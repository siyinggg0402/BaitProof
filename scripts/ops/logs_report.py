"""Is it running OK? Reads logs/events.jsonl (no message text is ever stored there).
Usage: python -m scripts.ops.logs_report [--hours 24] [--tail 20] [--errors]"""
import argparse
import time

import core  # noqa: F401
from core.obs import metrics


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--tail", type=int, default=0, help="also print the last N checks, one line each")
    ap.add_argument("--errors", action="store_true")
    a = ap.parse_args()
    events = metrics.read_events(since=time.time() - a.hours * 3600)
    s, h = metrics.summarize(events), metrics.health(events)
    icon = {"green": "🟢", "amber": "🟠", "red": "🔴"}[h["status"]]
    print(f"{icon} {h['status'].upper()}  (last {a.hours:g}h, {s['checks']} checks)")
    for p in h["problems"]:
        print("   ⚠", p)
    print(f"\nverdicts      {s['verdicts']}\nconfidence    {s['confidence']}   avg rounds {s['avg_rounds']}")
    print(f"latency       avg {s['latency_ms']['avg']}ms  p50 {s['latency_ms']['p50']}ms  p95 {s['latency_ms']['p95']}ms")
    l = s["llm"]
    print(f"model         {l['calls']} calls, {l['tokens_in']}+{l['tokens_out']} tokens ≈ ${l['est_cost_usd']}   fallbacks {l['fallbacks']}/{l['configured_checks']}")
    print(f"gate trips    {s['gate_trips'] or 'none'}")
    print(f"stage avg ms  {s['stage_avg_ms']}")
    print(f"tools         {s['tools'] or 'none'}")
    print(f"flywheel      {s['flywheel_stored']} stored   feedback 👍{s['feedback']['up']} 👎{s['feedback']['down']}   errors {s['errors']}")
    if a.errors or s["errors"]:
        for e in s["recent_errors"]:
            print("   error:", time.strftime("%H:%M:%S", time.localtime(e["ts"] or 0)), e["where"], e["type"])
    if a.tail:
        print("\nrecent checks:")
        for e in [x for x in events if x.get("kind") == "check"][-a.tail:]:
            flags = [f'{x["stage"]}:{x["status"]}' for x in e.get("stages", []) if x["status"] in ("flag", "block")]
            print(f'  {time.strftime("%H:%M:%S", time.localtime(e["ts"]))} {e["id"]} {e["verdict"]:12} {e["confidence"]:6} r{e.get("rounds", 1)} '
                  f'{e["latency_ms"]:>6}ms {e.get("tokens_in", 0)}+{e.get("tokens_out", 0)}tok {"AI" if e.get("used_ai") else "rules"} {flags or ""}')
    return 1 if h["status"] == "red" else 0


if __name__ == "__main__":
    raise SystemExit(main())
