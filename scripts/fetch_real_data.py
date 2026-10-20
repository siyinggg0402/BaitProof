"""Download the independent evaluation datasets listed in data/external/README.md. Files are untrusted: they are only ever read as text.
Usage: python -m scripts.fetch_real_data"""
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "external"
FILES = {
    "difraud_sms/test.jsonl": "https://huggingface.co/datasets/redasers/difraud/resolve/main/sms/test.jsonl",
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


def main() -> None:
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
