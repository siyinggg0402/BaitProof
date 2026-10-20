"""How does Baitproof behave on languages it has no rules for? Uses the machine-translated UCI SMS set (data/external/multilingual_sms, see
`python -m scripts.data.fetch --multilingual`): the same real messages in 13 languages. Compares a plain model call with the pipeline.
CAVEATS: machine translation is noisy and the scams are 2003-2012 British premium-rate SMS, so this checks that nothing breaks (no scam called
safe, few false alarms) in each language; it is NOT a measure of how well Chinese scams in the wild are caught (see tests/data/zh/holdout.py).
Usage: python -m scripts.eval.multilingual [--n 40] [--langs zh,id,ja,...] [--modes llm,full] [--workers 4]"""
import argparse
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.ai import llm
from core.lang.text import detect
from scripts import common

ROWS = Path(__file__).resolve().parents[2] / "data" / "external" / "multilingual_sms" / "rows.jsonl"
EXPECT = {"zh": "zh", "id": "ms", "ja": "ja", "ko": "ko", "hi": "hi", "ar": "ar", "ru": "ru", "bn": "bn"}  # others are Latin script: just "not English-only"


def load(lang: str) -> list[tuple[bool, str]]:
    out = []
    for line in ROWS.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        t = (r.get(lang) or "").strip()
        if len(t) >= 15 and t.lower() != (r["en"] or "").strip().lower():  # drop rows the translation left in English
            out.append((r["label"] == "spam", t))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40, help="scams and genuine messages per language")
    ap.add_argument("--langs", default="zh,id,ja,ko,hi,ar,es,fr")
    ap.add_argument("--modes", default="llm,full")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    if not llm.available():
        raise SystemExit("needs the model configured (NEBIUS_API_KEY)")
    print(common.header("lang  detected  system", width=22))
    for lang in a.langs.split(","):
        rows = load(lang)
        rnd = random.Random(a.seed)
        scams, hams = [r for r in rows if r[0]], [r for r in rows if not r[0]]
        sample = rnd.sample(scams, min(a.n, len(scams))) + rnd.sample(hams, min(a.n, len(hams)))
        det = sum(detect(t) == EXPECT.get(lang, detect(t)) for _, t in sample) / len(sample)
        for mode in a.modes.split(","):
            t0 = time.time()
            fn = common.plain_verdict if mode == "llm" else common.pipeline_verdict
            with ThreadPoolExecutor(a.workers) as ex:
                vs = list(ex.map(lambda r: fn(r[1]), sample))
            print(common.row(f"{lang:5} {det:>7.0%}  {mode}", common.tally(zip((s for s, _ in sample), vs)), time.time() - t0, width=22))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
