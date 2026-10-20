"""Run the held-out sets through the LIVE model, with a hard token budget so the credit is protected.
Usage: python -m scripts.eval.live [--n 12] [--max-tokens 100000] [--set 1|2]
Prints verdicts next to the offline-rules verdict so you can see what the model adds. Never prints the key."""
import argparse
import random

import core  # noqa: F401
from core.ai import llm
from core.obs.metrics import cost_usd
from core.pipelines.check import check_message
from tests.data.en import heldout_1 as heldout, heldout_2 as heldout2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12, help="messages per class (scam/legit)")
    ap.add_argument("--max-tokens", type=int, default=100_000)
    ap.add_argument("--set", type=int, default=2)
    a = ap.parse_args()
    if not llm.available():
        print("LLM not configured (.env)."); return 1
    ds = heldout2 if a.set == 2 else heldout
    scams = [t[0] if isinstance(t, tuple) else t for t in ds.SCAMS]
    legit = list(ds.LEGIT)
    random.Random(1).shuffle(scams); random.Random(1).shuffle(legit)
    live_safe_scam, live_alarm = 0, 0
    for label, items in (("SCAM", scams[: a.n]), ("LEGIT", legit[: a.n])):
        for text in items:
            if llm.USAGE["prompt_tokens"] + llm.USAGE["completion_tokens"] > a.max_tokens:
                print(f"\n⛔ token budget {a.max_tokens} reached, stopping early."); break
            r = check_message(text, store=False, log=False)
            steps = {s.stage: s for s in r.trace}
            ai = "AI" if r.used_ai else "rules-only"
            loops = [x for x in r.trace if x.stage == "loop"]
            print(f"{label:5} {r.verdict.value:12} {r.confidence:6} r{len(loops) + 1} {ai:10} {text[:52]!r}")
            for x in loops:
                print(f"        ↳ {x.detail[:150]}")
            if label == "SCAM" and r.verdict.value == "safe": live_safe_scam += 1
            if label == "LEGIT" and r.verdict.value in ("scam", "likely_scam"): live_alarm += 1
            if "critic" in steps and steps["critic"].status == "flag": print(f"        critic: {steps['critic'].detail}")
    u = llm.USAGE
    print(f"\nFALSE-SAFE scams: {live_safe_scam} (must be 0)   false alarms on legit: {live_alarm}")
    print(f"calls={u['calls']} tokens in={u['prompt_tokens']} out={u['completion_tokens']}  est. cost ≈ ${cost_usd(u['prompt_tokens'], u['completion_tokens']):.4f} (BAITPROOF_PRICE_IN/OUT set the price)")
    return 1 if live_safe_scam else 0


if __name__ == "__main__":
    raise SystemExit(main())
