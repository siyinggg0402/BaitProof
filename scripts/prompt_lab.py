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

LEGACY_REV = "4ce172c"  # the patchwork prompt from before the catalogue rewrite


def _legacy_prompt() -> str:
    import subprocess

    src = subprocess.run(["git", "show", f"{LEGACY_REV}:core/ai/prompts.py"], capture_output=True, text=True, check=True).stdout
    ns: dict = {}
    exec(compile(src, "legacy_prompts", "exec"), ns)  # our own repo history, not third-party code
    return ns["CHECK_SYSTEM"]


def user_text(system_name: str, text: str) -> str:
    """What the pipeline would show the model: for 'current' the purpose guidance + intent facts; for 'legacy' the old, simpler context."""
    from core.pipelines.check import analysis, intent as intent_stage
    from core.pipelines.check.ingest import ingest
    from core.pipelines.check.tools import Findings

    ing = ingest(text)
    it = intent_stage._heuristic(ing)
    f = Findings(hosts=list(ing.entities.hosts))
    if system_name == "legacy":
        return f"MESSAGE:\n{ing.redacted}\n\nINTENT (from rules): {it.summary()}\nTOOL FINDINGS (trusted):\nno deterministic findings"
    import os

    os.environ["BAITPROOF_FEWSHOT_MODE"] = "knn" if system_name == "fewshot-knn" else "balanced"
    return analysis.build_user(ing, it, f, examples=system_name.startswith("fewshot"))


VARIANTS = {"current": CHECK_SYSTEM, "fewshot": CHECK_SYSTEM, "fewshot-knn": CHECK_SYSTEM, "legacy": None}  # legacy loaded lazily from git; fewshot = current + retrieved examples


def ask(name: str, text: str) -> str:
    system = VARIANTS[name] or _legacy_prompt()
    try:
        return llm.chat_json(system, user_text(name, text), heavy=True, purpose="lab").get("verdict", "unsure")
    except llm.LLMUnavailable:
        return "error"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default="current,legacy")
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
                vs = list(ex.map(lambda r: ask(name, r[1]), rows))
            for label, want in (("scams  ", True), ("genuine", False)):
                c = collections.Counter(("scam" if v == "likely_scam" else v) for (s, _), v in zip(rows, vs) if s == want)
                print(f"  {name:9} {label}: " + "  ".join(f"{k}={c.get(k, 0)}" for k in ("scam", "unsure", "safe", "error")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
