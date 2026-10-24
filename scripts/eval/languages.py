"""One table for every language we care about: the same measurements (scams caught, "not sure", scams called safe, genuine cleared, false alarms) on the authored
sets for English, Chinese, Malay, Indonesian and Tamil, for the plain one-call model baseline, the whole pipeline, and (free) the rules alone.
The sets are written by us, not captured (see each file's note), so they are a development signal, not a benchmark; a set that was used to fix gaps says so.
Usage: python -m scripts.eval.languages [--sets en-hard3,zh-holdout,...] [--modes rules,llm,full] [--workers 6] [--misses] [--save out.json] [--diff old.json]
Model calls cost about $0.0003 each; `rules` never calls the model."""
import argparse
import importlib
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.ai import llm
from scripts import common

ROOT = Path(__file__).resolve().parents[2]


def from_module(name: str, scams: str = "SCAMS", legit: str = "LEGIT"):
    def load():
        m = importlib.import_module(name)
        rows = []
        for is_scam, items in ((True, getattr(m, scams)), (False, getattr(m, legit))):
            for i, item in enumerate(items):  # (tag, text) in most sets, (text, tag) in the English held-out scams and a bare text in their genuine ones
                tag, text = ("", item) if isinstance(item, str) else (item if len(item[1]) >= len(item[0]) else item[::-1])
                rows.append((is_scam, f"{name.rsplit('.', 1)[-1]}-{'s' if is_scam else 'g'}{i}-{tag}", text))
        return rows
    return load


def several(*loaders):
    return lambda: [row for load in loaders for row in load()]


def tamil_seeds():
    """data/seeds/ta.json: the practice bank (t01-t42 scams, t43-t56 genuine; t57-t62 are 'check first', left out of the counts)."""
    out = []
    for r in json.loads((ROOT / "data" / "seeds" / "ta.json").read_text(encoding="utf-8")):
        if r.get("truth") == "unsure":
            continue
        out.append((bool(r["is_scam"]), r["id"], r["text"]))
    return out


def real_sms(n: int = 100, seed: int = 11):
    """A fresh random sample of the DIFrauD train split (real messages, never used to tune anything): needs `python -m scripts.data.fetch`."""
    def load():
        from scripts.eval.real import load as real_load
        rows = real_load("smstrain")
        rnd = random.Random(seed)
        scams, hams = [r for r in rows if r[0]], [r for r in rows if not r[0]]
        return [(True, f"s{i}", t) for i, (_, t) in enumerate(rnd.sample(scams, n))] + [(False, f"g{i}", t) for i, (_, t) in enumerate(rnd.sample(hams, n))]
    return load


SETS = {
    "en-hard3": from_module("tests.data.en.hard_3"),
    "en-heldout": several(from_module("tests.data.en.heldout_1"), from_module("tests.data.en.heldout_2")),
    "en-real": real_sms(),
    "en-sg": from_module("tests.data.en.sg"),
    "zh-holdout": from_module("tests.data.zh.holdout"),
    "zh-fresh": from_module("tests.data.zh.fresh"),
    "ms-holdout": from_module("tests.data.ms.holdout"),
    "ms-fresh": from_module("tests.data.ms.fresh"),
    "id-dev": from_module("tests.data.id.dev"),
    "id-holdout": from_module("tests.data.id.holdout"),
    "id-fresh": from_module("tests.data.id.fresh"),
    "ta-seeds": tamil_seeds,
    "ta-dev": from_module("tests.data.ta.dev"),
    "ta-holdout": from_module("tests.data.ta.holdout"),
}
DEFAULT = "en-hard3,en-heldout,zh-holdout,ms-holdout,ms-fresh,id-dev,ta-seeds,ta-dev"


def run(mode: str, rows, workers: int):
    fn = common.plain_verdict if mode == "llm" else common.pipeline_verdict
    if mode == "rules":
        with common.offline(net=True):
            with ThreadPoolExecutor(workers) as ex:
                return list(ex.map(lambda r: fn(r[2]), rows))
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(lambda r: fn(r[2]), rows))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", default=DEFAULT)
    ap.add_argument("--modes", default="rules,llm,full")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--misses", action="store_true", help="list every message the pipeline got wrong (or only called not-sure)")
    ap.add_argument("--unsure", action="store_true", help="with --misses, also list the genuine messages the pipeline did not clear")
    ap.add_argument("--save", help="write every verdict to this JSON file")
    ap.add_argument("--diff", help="compare the pipeline's verdicts with an earlier --save file")
    a = ap.parse_args()
    modes = [m for m in a.modes.split(",") if m]
    if any(m != "rules" for m in modes) and not llm.available():
        raise SystemExit("needs the model configured (NEBIUS_API_KEY) for the llm and full modes")
    old = json.loads(Path(a.diff).read_text()) if a.diff else {}
    saved: dict = {}
    print(common.header("set / system", width=22))
    for name in a.sets.split(","):
        rows = SETS[name]()
        saved[name] = {}
        for mode in modes:
            t0 = time.time()
            sp = common.Spend() if mode != "rules" else None
            vs = run(mode, rows, a.workers)
            print(common.row(f"{name} {mode}", common.tally(zip((r[0] for r in rows), vs)), time.time() - t0, sp.usd if sp else None, width=22))
            saved[name][mode] = {r[1]: v for r, v in zip(rows, vs)}
            if mode == "full" and (a.misses or name in old):
                for (is_scam, tag, text), v in zip(rows, vs):
                    was = old.get(name, {}).get("full", {}).get(tag)
                    changed = was is not None and was != v
                    wrong = (is_scam and v != "scam") or (not is_scam and v == "scam") or (is_scam and v == "safe") or (a.unsure and not is_scam and v != "safe")
                    if (a.misses and wrong) or changed:
                        kind = "SCAM " if is_scam else "GENUINE"
                        print(f"   {'~' if changed else ' '} {kind} {tag}: {v}" + (f" (was {was})" if changed else "") + f"  | {text[:90]!r}")
    if a.save:
        Path(a.save).write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
