"""python -m scripts.eval_offline   (rules only, free). For the live model use scripts.eval_live."""
import os

os.environ["NEBIUS_API_KEY"] = ""  # force rules-only so this never spends model credit (dotenv won't override a set var)
import core  # noqa: F401
from core.pipelines.check import evaluate

r = evaluate.run()
print(f"scams: {r['scams']}  false-SAFE: {r['false_safe']} (must be 0)  flagged scam/likely: {r['scam_caught_confident']}")
print(f"legit: {r['legit']}  false alarms: {r['false_alarm']}  cleared as safe: {r['legit_cleared']}")
if r["missed_ids"]:
    print("MISSED:", r["missed_ids"])
raise SystemExit(1 if r["false_safe"] else 0)
