"""Measure the MODEL's verdict (one call, no pipeline) for prompt variants on real samples. Tune on --seed A, confirm on a disjoint --seed B.
Usage: python -m scripts.prompt_lab --variants current,decisive --n 80 --seed 7 [--exclude-seed 7]"""
import argparse
import collections
from concurrent.futures import ThreadPoolExecutor

import core  # noqa: F401
from core.ai import llm
from core.ai.prompts import CHECK_SYSTEM
from core.domain.privacy import redact
from scripts import eval_real

# 'terse' is the pre-calibration wording (no "be decisive" paragraph), kept so a change can always be compared against it.
TERSE = CHECK_SYSTEM[: CHECK_SYSTEM.index("Be decisive.")] + CHECK_SYSTEM[CHECK_SYSTEM.index("Rules: NEVER answer"):]

VARIANTS = {"current": CHECK_SYSTEM, "terse": TERSE}


def ask(system: str, text: str) -> str:
    try:
        return llm.chat_json(system, "MESSAGE:\n" + redact(text), heavy=True, purpose="lab").get("verdict", "unsure")
    except llm.LLMUnavailable:
        return "error"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default="current,terse")
    ap.add_argument("--n", type=int, default=80)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--exclude-seed", type=int, default=None, help="drop messages already in that seed's sample (a disjoint confirmation set)")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    for src in ("sms", "fin"):
        pool = eval_real.load(src)
        if a.exclude_seed is not None:
            used = {t for _, t in eval_real.sample(pool, 100, a.exclude_seed)}
            pool = [r for r in pool if r[1] not in used]
        rows = eval_real.sample(pool, a.n, a.seed)
        print(f"\n== {src}: {sum(r[0] for r in rows)} scams + {sum(not r[0] for r in rows)} genuine (seed {a.seed})")
        for name in a.variants.split(","):
            with ThreadPoolExecutor(a.workers) as ex:
                vs = list(ex.map(lambda r: ask(VARIANTS[name], r[1]), rows))
            for label, want in (("scams  ", True), ("genuine", False)):
                c = collections.Counter(("scam" if v == "likely_scam" else v) for (s, _), v in zip(rows, vs) if s == want)
                print(f"  {name:9} {label}: " + "  ".join(f"{k}={c.get(k, 0)}" for k in ("scam", "unsure", "safe", "error")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
