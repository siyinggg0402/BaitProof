"""Is the architecture actually better than 'just call an LLM'? Runs the HARD set through three systems:
  rules  - the built-in rules only (free)
  llm    - ONE plain model call, no intent/tools/evidence/gates (the naive baseline)
  full   - the whole pipeline (evidence ledger, tools, loop, gates)
Usage: python -m scripts.compare [--no-net] [--max-tokens 250000]"""
import argparse
import os
import time

import core  # noqa: F401
from core.ai import llm
from core.domain.schemas import Verdict as V
from core.domain.privacy import redact
from tests.data import hard_set, hard_set_2, hard_set_3

BASELINE_SYSTEM = """You are a scam detector. Decide whether the message is a scam. Return ONLY JSON: {"verdict": "scam" | "safe" | "unsure"}."""
FLAGGED = ("scam", "likely_scam")


def baseline(text: str) -> str:
    try:
        v = llm.chat_json(BASELINE_SYSTEM, "MESSAGE:\n" + redact(text), heavy=True, purpose="baseline").get("verdict", "unsure")
    except llm.LLMUnavailable:
        return "error"
    return v if v in ("scam", "safe", "unsure") else "unsure"


def run_mode(mode: str, ds=None):
    ds = ds or hard_set
    from core.pipelines.check import check_message

    rows = []
    for kind, items in (("scam", ds.SCAMS), ("legit", ds.LEGIT)):
        for tag, text in items:
            t0 = time.time()
            if mode == "llm":
                v, rounds = baseline(text), 1
            else:
                r = check_message(text, store=False, log=False)
                v, rounds = r.verdict.value, 1 + sum(1 for s in r.trace if s.stage == "loop")
            rows.append({"kind": kind, "tag": tag, "verdict": "scam" if v == "likely_scam" else v, "raw": v, "rounds": rounds, "secs": time.time() - t0})
    return rows


def score(rows):
    sc, lg = [r for r in rows if r["kind"] == "scam"], [r for r in rows if r["kind"] == "legit"]
    return {
        "scams": len(sc), "caught": sum(r["verdict"] == "scam" for r in sc), "scam_unsure": sum(r["verdict"] == "unsure" for r in sc),
        "FALSE_SAFE": sum(r["verdict"] == "safe" for r in sc),
        "legit": len(lg), "cleared": sum(r["verdict"] == "safe" for r in lg), "legit_unsure": sum(r["verdict"] == "unsure" for r in lg),
        "FALSE_ALARM": sum(r["verdict"] == "scam" for r in lg),
        "avg_secs": round(sum(r["secs"] for r in rows) / len(rows), 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-net", action="store_true", help="disable RDAP/DNS lookups")
    ap.add_argument("--modes", default="rules,llm,full")
    ap.add_argument("--set", type=int, default=1, choices=(1, 2, 3), help="1 = dev set, 2 = contaminated holdout, 3 = clean holdout")
    a = ap.parse_args()
    if a.no_net:
        os.environ["BAITPROOF_NET_TOOLS"] = "0"
    ds = {1: hard_set, 2: hard_set_2, 3: hard_set_3}[a.set]
    results = {}
    for mode in a.modes.split(","):
        if mode == "rules":
            keep = os.environ.get("NEBIUS_API_KEY")
            os.environ["NEBIUS_API_KEY"] = ""
            results[mode] = run_mode("full", ds)
            os.environ["NEBIUS_API_KEY"] = keep or ""
        else:
            if not llm.available():
                print(f"skipping '{mode}': model not configured"); continue
            before = dict(llm.USAGE)
            results[mode] = run_mode(mode, ds)
            results[mode + "_tok"] = (llm.USAGE["prompt_tokens"] - before["prompt_tokens"], llm.USAGE["completion_tokens"] - before["completion_tokens"])
    print(f"\n{'system':8} {'scams caught':>13} {'unsure':>7} {'FALSE-SAFE':>11} | {'legit cleared':>14} {'unsure':>7} {'FALSE-ALARM':>12} | {'avg s':>6}")
    for mode in ("rules", "llm", "full"):
        if mode in results:
            s = score(results[mode])
            print(f"{mode:8} {s['caught']:>6}/{s['scams']:<6} {s['scam_unsure']:>7} {s['FALSE_SAFE']:>11} | {s['cleared']:>7}/{s['legit']:<6} {s['legit_unsure']:>7} {s['FALSE_ALARM']:>12} | {s['avg_secs']:>6}")
    for mode in ("llm", "full"):
        if mode + "_tok" in results:
            tin, tout = results[mode + "_tok"]
            print(f"  {mode}: {tin}+{tout} tokens ≈ ${(tin * .06 + tout * .24) / 1e6:.4f}")
    print("\nWHERE THE SYSTEMS DISAGREE WITH THE TRUTH:")
    for mode in ("rules", "llm", "full"):
        for r in results.get(mode, []):
            bad = (r["kind"] == "scam" and r["verdict"] != "scam") or (r["kind"] == "legit" and r["verdict"] == "scam")
            if bad:
                tag = "MISSED" if r["kind"] == "scam" else "FALSE ALARM"
                print(f"  {mode:6} {tag:11} {r['verdict']:7} {r['tag']}")
    full = results.get("full", [])
    return 1 if any(r["kind"] == "scam" and r["verdict"] == "safe" for r in full) else 0


if __name__ == "__main__":
    raise SystemExit(main())
