"""Turn the event log into numbers an operator can read: is it running OK, what is it costing, where do gates trip."""
from __future__ import annotations

import json
import os
import time
from collections import Counter, defaultdict

from .logger import DROPPED, path

PRICE_IN, PRICE_OUT = float(os.getenv("BAITPROOF_PRICE_IN", "0.06")), float(os.getenv("BAITPROOF_PRICE_OUT", "0.24"))  # $/1M tok, estimate


def cost_usd(tokens_in: int, tokens_out: int) -> float:
    return (tokens_in * PRICE_IN + tokens_out * PRICE_OUT) / 1e6


def read_events(limit: int = 20000, since: float | None = None) -> list[dict]:
    out: list[dict] = []
    for p in (path() + ".1", path()):  # oldest first
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    if since is None or e.get("ts", 0) >= since:
                        out.append(e)
        except FileNotFoundError:
            continue
    return out[-limit:]


def _pct(vals: list[float], q: float) -> int:
    if not vals:
        return 0
    s = sorted(vals)
    return int(s[min(len(s) - 1, int(q * len(s)))])


def summarize(events: list[dict]) -> dict:
    checks = [e for e in events if e.get("kind") == "check"]
    n = len(checks)
    lat = [c.get("latency_ms", 0) for c in checks]
    tin = sum(c.get("tokens_in", 0) for c in checks)
    tout = sum(c.get("tokens_out", 0) for c in checks)
    configured = [c for c in checks if c.get("ai_configured")]
    fallbacks = [c for c in configured if not c.get("used_ai")]
    trips: Counter = Counter()
    stage_ms: dict[str, list[int]] = defaultdict(list)
    for c in checks:
        for s in c.get("stages", []):
            stage_ms[s["stage"]].append(s.get("ms", 0))
            if s.get("status") in ("flag", "block"):
                trips[f'{s["stage"]}:{s["status"]}'] += 1
    tools: dict[str, dict] = defaultdict(lambda: {"calls": 0, "ok": 0, "ms": 0})
    for c in checks:
        for t in c.get("tools", []):
            d = tools[t["tool"]]
            d["calls"] += 1
            d["ok"] += 1 if t.get("ok") else 0
            d["ms"] += t.get("ms", 0)
    fb = Counter(e.get("rating") for e in events if e.get("kind") == "feedback")
    errors = [e for e in events if e.get("kind") == "error"]
    return {
        "checks": n,
        "verdicts": dict(Counter(c.get("verdict") for c in checks)),
        "confidence": dict(Counter(c.get("confidence") for c in checks)),
        "avg_rounds": round(sum(c.get("rounds", 1) for c in checks) / n, 2) if n else 0,
        "latency_ms": {"avg": int(sum(lat) / n) if n else 0, "p50": _pct(lat, 0.5), "p95": _pct(lat, 0.95)},
        "llm": {"configured_checks": len(configured), "fallbacks": len(fallbacks),
                "fallback_rate": round(len(fallbacks) / len(configured), 3) if configured else 0.0,
                "calls": sum(c.get("llm_calls", 0) for c in checks), "tokens_in": tin, "tokens_out": tout,
                "est_cost_usd": round(cost_usd(tin, tout), 5)},
        "gate_trips": dict(trips.most_common(12)),
        "stage_avg_ms": {k: int(sum(v) / len(v)) for k, v in stage_ms.items()},
        "tools": {k: {"calls": v["calls"], "ok_rate": round(v["ok"] / v["calls"], 2), "avg_ms": int(v["ms"] / v["calls"])} for k, v in tools.items()},
        "flywheel_stored": sum(1 for c in checks if c.get("flywheel")),
        "feedback": {"up": fb.get("up", 0), "down": fb.get("down", 0)},
        "errors": len(errors),
        "recent_errors": [{"ts": e.get("ts"), "where": e.get("where"), "type": e.get("type")} for e in errors[-5:]],
        "log_writes_dropped": DROPPED["count"],
    }


def health(events: list[dict] | None = None) -> dict:
    """Plain-English status for the operator: green/amber/red with reasons."""
    events = events if events is not None else read_events(since=time.time() - 3600)
    s = summarize(events)
    problems: list[str] = []
    if s["llm"]["configured_checks"] >= 5 and s["llm"]["fallback_rate"] > 0.3:
        problems.append(f'model fell back to rules on {int(s["llm"]["fallback_rate"] * 100)}% of checks (network, key or JSON problem)')
    if s["errors"]:
        problems.append(f'{s["errors"]} internal error(s) in the last hour')
    if s["latency_ms"]["p95"] > 30000:
        problems.append(f'slow: p95 {s["latency_ms"]["p95"] // 1000}s per check')
    if s["log_writes_dropped"]:
        problems.append("some log lines could not be written (disk or permissions)")
    fb = s["feedback"]
    if fb["up"] + fb["down"] >= 10 and fb["down"] / (fb["up"] + fb["down"]) > 0.3:
        problems.append("more than 30% of feedback says the verdict was wrong")
    return {"status": "red" if s["errors"] else ("amber" if problems else "green"), "problems": problems, "last_hour": s}
