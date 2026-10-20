"""How does Baitproof behave on languages it has no rules for? Uses the machine-translated UCI SMS set (data/external/multilingual_sms, see
`python -m scripts.fetch_real_data --multilingual`): the same real messages in 13 languages. Compares a plain model call with the pipeline.
CAVEATS: machine translation is noisy and the scams are 2003-2012 British premium-rate SMS, so this checks that nothing breaks (no scam called
safe, few false alarms) in each language; it is NOT a measure of how well Chinese scams in the wild are caught (see tests/data/zh_holdout.py).
Usage: python -m scripts.eval_multilingual [--n 40] [--langs zh,id,ja,...] [--modes llm,full] [--workers 4]"""
import argparse
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import core  # noqa: F401
from core.ai import llm
from core.domain.lang import detect
from core.domain.privacy import redact

ROWS = Path(__file__).resolve().parents[1] / "data" / "external" / "multilingual_sms" / "rows.jsonl"
BASELINE_SYSTEM = """You are a scam detector. Decide whether the message is a scam. Return ONLY JSON: {"verdict": "scam" | "safe" | "unsure"}."""
EXPECT = {"zh": "zh", "id": "ms", "ja": "ja", "ko": "ko", "hi": "hi", "ar": "ar", "ru": "ru", "bn": "bn"}  # others are Latin script: just "not English-only"


def load(lang: str) -> list[tuple[bool, str]]:
    out = []
    for line in ROWS.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        t = (r.get(lang) or "").strip()
        if len(t) >= 15 and t.lower() != (r["en"] or "").strip().lower():  # drop rows the translation left in English
            out.append((r["label"] == "spam", t))
    return out


def verdict(mode: str, text: str) -> str:
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
    print(f"{'lang':5} {'detected':>9} | {'system':6} {'caught':>9} {'unsure':>6} {'FALSE-SAFE':>10} | {'cleared':>9} {'unsure':>6} {'FALSE-ALARM':>11} | {'secs':>5}")
    for lang in a.langs.split(","):
        rows = load(lang)
        rnd = random.Random(a.seed)
        scams, hams = [r for r in rows if r[0]], [r for r in rows if not r[0]]
        sample = rnd.sample(scams, min(a.n, len(scams))) + rnd.sample(hams, min(a.n, len(hams)))
        det = sum(detect(t) == EXPECT.get(lang, detect(t)) for _, t in sample) / len(sample)
        for mode in a.modes.split(","):
            t0 = time.time()
            with ThreadPoolExecutor(a.workers) as ex:
                vs = list(ex.map(lambda r: verdict(mode, r[1]), sample))
            sc = [v for (s, _), v in zip(sample, vs) if s]
            hm = [v for (s, _), v in zip(sample, vs) if not s]
            f = lambda xs, k: sum(x == k for x in xs)  # noqa: E731
            print(f"{lang:5} {det:>8.0%} | {mode:6} {f(sc, 'scam'):>4}/{len(sc):<4} {f(sc, 'unsure'):>6} {f(sc, 'safe'):>10} | {f(hm, 'safe'):>4}/{len(hm):<4} {f(hm, 'unsure'):>6} {f(hm, 'scam'):>11} | {time.time() - t0:>5.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
