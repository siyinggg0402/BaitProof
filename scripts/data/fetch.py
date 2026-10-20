"""Download the independent evaluation datasets listed in data/external/README.md. Files are untrusted: they are only ever read as text.
Usage: python -m scripts.data.fetch                 (English datasets)
       python -m scripts.data.fetch --multilingual  (the machine-translated SMS set, 13 languages; needs pyarrow)"""
import sys
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "external"
FILES = {
    "difraud_sms/test.jsonl": "https://huggingface.co/datasets/redasers/difraud/resolve/main/sms/test.jsonl",
    "difraud_sms/train.jsonl": "https://huggingface.co/datasets/redasers/difraud/resolve/main/sms/train.jsonl",
    "difraud_sms/validation.jsonl": "https://huggingface.co/datasets/redasers/difraud/resolve/main/sms/validation.jsonl",
    "difraud_sms/LICENSE.txt": "https://huggingface.co/datasets/redasers/difraud/resolve/main/LICENSE.txt",
    "mendeley_financial/financial_scams.csv": "https://data.mendeley.com/public-files/datasets/znsk27yk3h/files/d8cdbed5-0c31-4010-82e7-ed432c4bc313/file_downloaded",
}


def fetch(url: str, dest: Path, tries: int = 3) -> None:
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Baitproof-eval/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read(20_000_000)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return
        except Exception as e:
            print(f"  attempt {i + 1} failed: {type(e).__name__}")
    raise SystemExit(f"could not download {url}")


ML_DATASET = "dbarbedillo/SMS_Spam_Multilingual_Collection_Dataset"  # the UCI SMS Spam Collection, machine-translated (GPL-3.0): a robustness check, not real local scams
ML_LANGS = ["zh", "id", "ja", "ko", "hi", "ar", "es", "fr", "de", "ru", "pt", "tr", "bn"]


def fetch_multilingual() -> None:
    """Download the dataset's parquet file (about 8 MB) and keep the label plus one text column per language. Needs `pip install pyarrow`."""
    try:
        import io

        import pyarrow.parquet as pq
    except ImportError:
        raise SystemExit("this optional step needs pyarrow: pip install pyarrow")
    tmp = ROOT / "multilingual_sms" / "train.parquet"
    fetch(f"https://huggingface.co/datasets/{ML_DATASET}/resolve/refs%2Fconvert%2Fparquet/default/train/0000.parquet", tmp)
    table = pq.read_table(io.BytesIO(tmp.read_bytes())).to_pylist()
    out = [{"label": r["labels"], "en": r["text"], **{lang: r.get(f"text_{lang}") for lang in ML_LANGS}} for r in table]
    dest = ROOT / "multilingual_sms" / "rows.jsonl"
    dest.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in out), encoding="utf-8")
    tmp.unlink()
    print("ok:", len(out), "rows ->", dest)


def main() -> None:
    if "--multilingual" in sys.argv:
        return fetch_multilingual()
    manifest = {}
    for rel, url in FILES.items():
        dest = ROOT / rel
        print("fetching", rel)
        fetch(url, dest)
        manifest[rel] = {"sha256": hashlib.sha256(dest.read_bytes()).hexdigest(), "bytes": dest.stat().st_size, "url": url}
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print("ok:", {k: v["bytes"] for k, v in manifest.items()})


if __name__ == "__main__":
    main()
