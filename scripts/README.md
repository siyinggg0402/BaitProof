# scripts

Run everything from the repo root as `python -m scripts.<group>.<name>`. Nothing here is imported by the app.

| Command | What it does | Cost |
|---|---|---|
| `scripts.eval.compare --set 1\|2\|3 [--modes rules,llm,full] [--no-net]` | The hard sets (`tests/data/en/hard_*.py`) through the rules, one plain model call, and the whole pipeline. | cents |
| `scripts.eval.real --sources sms,smstrain,fin [--modes rules,llm,full] [--exclude-seed N]` | Real, independently collected messages (needs `scripts.data.fetch`). | cents |
| `scripts.eval.multilingual [--langs zh,id,ja,...]` | The same real SMS machine-translated into other languages: does anything break where there are no rules? | cents |
| `scripts.ops.make_vapid` | Make the site's Web Push (VAPID) keys and add them to `.env` if they are not there; never prints the private key. | free |
| `scripts.data.fetch [--multilingual]` | Download the third-party evaluation data into `data/external/` (never committed). | free |
| `scripts.data.seed_demo` | Put the local database in a believable mid-training state for the demo. | free |
| `scripts.ops.verify_setup [--list]` | Check the Nebius endpoint, the Nemotron model id and (if set) Tavily. Never prints the key. | one tiny call |
| `scripts.ops.refresh_blocklist [--status]` | Download the public phishing-site list (Phishing.Database, MIT) to `data/cache/`, or show how fresh it is. The app also does this daily. | one 11 MB download |

`scripts/common.py` holds what the evaluations share: the plain-model baseline prompt, verdict normalisation, the results table, and `offline()`,
which blanks the model key so a run can never spend credit. Prices come from `core.obs.metrics` (`BAITPROOF_PRICE_IN` / `BAITPROOF_PRICE_OUT`).
