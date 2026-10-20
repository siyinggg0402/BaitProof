"""Is the architecture actually better than 'just call an LLM'? Runs the HARD set through three systems:
  rules  - the built-in rules only (free)
  llm    - ONE plain model call, no intent/tools/evidence/gates (the naive baseline)
  full   - the whole pipeline (evidence ledger, tools, loop, gates)
Usage: python -m scripts.eval.compare [--no-net] [--max-tokens 250000]"""
import argparse
import os
import time

from core.ai import llm
from scripts import common
from tests.data.en import hard_1, hard_2, hard_3


def run_mode(mode: str, ds):
    """[(is_scam, tag, verdict, secs)] for one system over a labelled set."""
    rows = []
    for is_scam, items in ((True, ds.SCAMS), (False, ds.LEGIT)):
        for tag, text in items:
            t0 = time.time()
            rows.append((is_scam, tag, common.plain_verdict(text) if mode == "llm" else common.pipeline_verdict(text), time.time() - t0))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-net", action="store_true", help="disable RDAP/DNS lookups")
    ap.add_argument("--modes", default="rules,llm,full")
    ap.add_argument("--set", type=int, default=1, choices=(1, 2, 3), help="1 = dev set, 2 = contaminated holdout, 3 = holdout (a development set since one opener rule was added after it)")
    a = ap.parse_args()
    if a.no_net:
        os.environ["BAITPROOF_NET_TOOLS"] = "0"
    ds = {1: hard_1, 2: hard_2, 3: hard_3}[a.set]
    results, spend = {}, {}
    for mode in a.modes.split(","):
        if mode == "rules":
            with common.offline():
                results[mode] = run_mode("full", ds)
        elif not llm.available():
            print(f"skipping '{mode}': model not configured")
        else:
            spend[mode] = common.Spend()
            results[mode] = run_mode(mode, ds)
    print(f"\n{common.header()}")
    for mode, rows in results.items():
        print(common.row(mode, common.tally((r[0], r[2]) for r in rows), sum(r[3] for r in rows) / len(rows)))
    for mode, sp in spend.items():
        print(f"  {mode}: {sp.tokens[0]}+{sp.tokens[1]} tokens ≈ ${sp.usd:.4f}")
    print("\nWHERE THE SYSTEMS DISAGREE WITH THE TRUTH:")
    for mode, rows in results.items():
        for is_scam, tag, v, _ in rows:
            if (is_scam and v != "scam") or (not is_scam and v == "scam"):
                print(f"  {mode:6} {'MISSED' if is_scam else 'FALSE ALARM':11} {v:7} {tag}")
    return 1 if any(r[0] and r[2] == "safe" for r in results.get("full", [])) else 0


if __name__ == "__main__":
    raise SystemExit(main())
