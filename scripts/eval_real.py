"""Evaluate on REAL, independently collected messages (see data/external/README.md). Run scripts.fetch_real_data first.
Compares: rules only | one plain LLM call (naive baseline) | the full pipeline.
Usage: python -m scripts.eval_real [--n 60] [--sources sms,fin] [--modes rules,llm,full] [--workers 4] [--seed 7]"""
import argparse
import csv
import json
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import core  # noqa: F401
from core.ai import llm
from core.domain.privacy import redact

EXT = Path(__file__).resolve().parents[1] / "data" / "external"
BASELINE_SYSTEM = """You are a scam detector. Decide whether the message is a scam. Return ONLY JSON: {"verdict": "scam" | "safe" | "unsure"}."""
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
    if mode == "llm":
        try:
            v = llm.chat_json(BASELINE_SYSTEM, "MESSAGE:\n" + redact(text), heavy=True, purpose="baseline").get("verdict", "unsure")
        except llm.LLMUnavailable:
            return "error"
        return v if v in ("scam", "safe", "unsure") else "unsure"
    from core.pipelines.check import check_message

    try:
        v = check_message(text, store=False, log=False).verdict.value
    except Exception:
        return "error"
    return "scam" if v == "likely_scam" else ("unsure" if v == "victim_support" else v)


def run(mode: str, rows, workers: int):
    t0 = time.time()
    if mode == "rules":
        keep, os.environ["NEBIUS_API_KEY"] = os.environ.get("NEBIUS_API_KEY", ""), ""
    with ThreadPoolExecutor(max_workers=1 if mode == "rules" else workers) as ex:
        verdicts = list(ex.map(lambda r: verdict_of(mode, r[1]), rows))
    if mode == "rules":
        os.environ["NEBIUS_API_KEY"] = keep
    return verdicts, time.time() - t0


def table(name, rows, verdicts):
    sc = [v for (s, _), v in zip(rows, verdicts) if s]
    hm = [v for (s, _), v in zip(rows, verdicts) if not s]
    f = lambda xs, k: sum(x == k for x in xs)  # noqa: E731
    return {"mode": name, "scams": len(sc), "caught": f(sc, "scam"), "scam_unsure": f(sc, "unsure"), "FALSE_SAFE": f(sc, "safe"),
            "ham": len(hm), "cleared": f(hm, "safe"), "ham_unsure": f(hm, "unsure"), "FALSE_ALARM": f(hm, "scam"), "errors": f(sc + hm, "error")}


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
        print(f"{'system':7} {'caught':>9} {'unsure':>7} {'FALSE-SAFE':>11} | {'cleared':>9} {'unsure':>7} {'FALSE-ALARM':>12} | {'secs':>6}")
        res = {}
        for mode in a.modes.split(","):
            if mode != "rules" and not llm.available():
                print(f"{mode}: model not configured"); continue
            before = dict(llm.USAGE)
            v, secs = run(mode, rows, a.workers)
            res[mode] = v
            t = table(mode, rows, v)
            tok = (llm.USAGE["prompt_tokens"] - before["prompt_tokens"], llm.USAGE["completion_tokens"] - before["completion_tokens"])
            print(f"{mode:7} {t['caught']:>4}/{t['scams']:<4} {t['scam_unsure']:>7} {t['FALSE_SAFE']:>11} | {t['cleared']:>4}/{t['ham']:<4} {t['ham_unsure']:>7} {t['FALSE_ALARM']:>12} | {secs:>6.0f}"
                  + (f"  ({t['errors']} errors)" if t["errors"] else "") + (f"  ≈${(tok[0] * .06 + tok[1] * .24) / 1e6:.4f}" if mode != "rules" else ""))
        if "full" in res:
            bad = [(s, t, v) for (s, t), v in zip(rows, res["full"]) if (s and v == "safe") or (not s and v == "scam")]
            print(f"\n  full pipeline mistakes ({len(bad)}), first {a.show}:")
            for s, t, v in bad[:a.show]:
                print(f"    {'MISSED (safe)' if s else 'FALSE ALARM'}: {t[:120]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
