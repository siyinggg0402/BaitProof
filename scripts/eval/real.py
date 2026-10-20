"""Evaluate on REAL, independently collected messages (see data/external/README.md). Run scripts.data.fetch first.
Compares: rules only | one plain LLM call (naive baseline) | the full pipeline.
Sources: sms (DIFrauD test split), smstrain / smsval (the fresh splits), fin (Mendeley financial, English rows).
Usage: python -m scripts.eval.real [--n 60] [--sources sms,fin] [--modes rules,llm,full] [--workers 4] [--seed 7]"""
import argparse
import csv
import json
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.ai import llm
from scripts import common

EXT = Path(__file__).resolve().parents[2] / "data" / "external"
WS = re.compile(r"\s+")


def load(source: str) -> list[tuple[bool, str]]:
    out = []
    if source in ("sms", "smstrain", "smsval"):  # disjoint random splits of the same SMS data: test (dev, studied), train (fresh), validation (fresh)
        split = {"sms": "test", "smstrain": "train", "smsval": "validation"}[source]
        for line in open(EXT / "difraud_sms" / f"{split}.jsonl", encoding="utf-8"):
            r = json.loads(line)
            out.append((r["label"] == 1, WS.sub(" ", r["text"]).strip()))
    elif source == "fin":
        for r in csv.DictReader(open(EXT / "mendeley_financial" / "financial_scams.csv", encoding="utf-8-sig", errors="replace")):
            t = WS.sub(" ", (r.get("message") or "")).strip()
            if t and sum(c.isascii() for c in t) / len(t) > 0.95:  # English rows only
                out.append((r["label"].strip().lower() == "scam", t))
    seen, clean = set(), []
    for is_scam, t in out:
        if len(t) >= 12 and not t.isdigit() and t.lower() not in seen:
            seen.add(t.lower())
            clean.append((is_scam, t))
    return clean


def sample(rows, n, seed):
    rnd = random.Random(seed)
    scams, hams = [r for r in rows if r[0]], [r for r in rows if not r[0]]
    return rnd.sample(scams, min(n, len(scams))) + rnd.sample(hams, min(n, len(hams)))


def verdict_of(mode: str, text: str) -> str:
    return common.plain_verdict(text) if mode == "llm" else common.pipeline_verdict(text)


def run(mode: str, rows, workers: int):
    t0 = time.time()
    if mode == "rules":
        with common.offline():  # rules only: no model, one at a time
            verdicts = [verdict_of("full", r[1]) for r in rows]
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            verdicts = list(ex.map(lambda r: verdict_of(mode, r[1]), rows))
    return verdicts, time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60, help="messages per class per source")
    ap.add_argument("--sources", default="sms,fin")
    ap.add_argument("--modes", default="rules,llm,full")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--show", type=int, default=12, help="how many mistakes of the full pipeline to print")
    ap.add_argument("--exclude-seed", type=int, default=None, help="drop every message that --seed N sampled (n=--n), for a disjoint fresh test")
    a = ap.parse_args()
    for src in a.sources.split(","):
        pool = load(src)
        if a.exclude_seed is not None:
            used = {t for _, t in sample(pool, a.n, a.exclude_seed)}
            pool = [r for r in pool if r[1] not in used]
        rows = sample(pool, a.n, a.seed)
        print(f"\n===== {src}: {sum(r[0] for r in rows)} scams + {sum(not r[0] for r in rows)} genuine (seed {a.seed}) =====")
        print(common.header(width=7))
        res = {}
        for mode in a.modes.split(","):
            if mode != "rules" and not llm.available():
                print(f"{mode}: model not configured"); continue
            spend = common.Spend()
            v, secs = run(mode, rows, a.workers)
            res[mode] = v
            print(common.row(mode, common.tally(zip((s for s, _ in rows), v)), secs, None if mode == "rules" else spend.usd, width=7))
        if "full" in res:
            bad = [(s, t, v) for (s, t), v in zip(rows, res["full"]) if (s and v == "safe") or (not s and v == "scam")]
            print(f"\n  full pipeline mistakes ({len(bad)}), first {a.show}:")
            for s, t, v in bad[:a.show]:
                print(f"    {'MISSED (safe)' if s else 'FALSE ALARM'}: {t[:120]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
