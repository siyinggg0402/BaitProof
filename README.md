# 🛡️ Baitproof

**A personal scam-defense coach for your family.** Forward a suspicious message and Baitproof tells you if it's a scam, points at the *one giveaway*, and adds that trick to your training. It learns which tricks *you* fall for, drills those, and lets you send a "can you spot the scam?" challenge to your parents.

*Hoxhunt for protecting your parents, not your payroll.*

Built for the Nebius x NVIDIA Global AI Hackathon 2026, track **Personal AI**. See [PLAN.md](PLAN.md) for the full design.

## Why not a detector / ChatGPT / Hoxhunt?
- **Detectors** tell you once and forget you. Baitproof makes you harder to fool next time.
- **Enterprise trainers** (Hoxhunt, KnowBe4) are sold to IT departments and drill synthetic scams. Baitproof is for families and drills the **real scams reaching your circle**.
- **ChatGPT** has no persistent model of you. Baitproof keeps a per-tactic mastery model and a Baitproof score.

## Stack
- **Inference:** Nebius Token Factory (OpenAI-compatible) with **NVIDIA Nemotron**. Model id: *to be confirmed in Phase 0* (`python -m scripts.verify_setup --list`); this README must name the verified id before submission.
- **Verification (optional):** Tavily. **State:** SQLite. **Web:** FastAPI + Jinja + vanilla JS (large type, high contrast, read-aloud).
- Without keys the app runs in **offline mode** using built-in rule checks, so it never crashes or gives a bare all-clear.

## Architecture
```
 paste message ─▶ CHECK ──▶ verdict + the one tell + safe action
                   │ tactics + abstracted example
                   ▼
        threat library ◀── curated seed bank
        personal model (per-tactic mastery, SQLite)
                   │ weakest + due + "just seen in real life"
                   ▼
                 TRAIN ──▶ drills ─▶ grading ─▶ model + Baitproof score ─▶ SHARE card
```
`core/` is channel-agnostic and split by role:
```
core/domain/     tactics.py (12-tactic controlled vocabulary), schemas.py
core/storage/    db.py, library.py (threat library + PII scrub), model.py (personal model + score)
core/ai/         llm.py (Nebius client), prompts.py, verify.py (Tavily)
core/pipelines/  train.py, challenge.py, evaluate.py
core/pipelines/check/  the gated Check pipeline (below)
```

## How Check decides (gated pipeline)
```
ingest ─▶ victim triage ─▶ intent ─▶ tools ─▶ analysis ─▶ grounding ─▶ arbiter ─▶ critic ─▶ flywheel gate
 gate        branch        what is   allow-    rules +     quotes must   asymmetric  2nd look   only confident
 (injection,               it asking listed,   model       exist in the  table: safe  before     scams may enter
 entities)                 me to DO? budgeted  proposes    message       must be     "safe"     the training
                                                                         earned                  library
```
The model proposes; deterministic gates decide. The model can add suspicion but never clear hard evidence, an
invented red flag with no matching words is dropped, "safe" needs a clean intent + no links + a second reviewer,
and a low-confidence verdict never becomes a training example. The UI shows the trace ("How I decided").
`python -m scripts.eval_offline` reports the false-SAFE rate (must be 0); `python -m scripts.eval_live` does the same against the live model with a hard token budget.

### Measured accuracy (offline rules; the live model is not yet tuned)
| Set | Scams | Missed as "safe" | Flagged | Legit false alarms |
|---|---|---|---|---|
| Seed bank (in-sample) | 36 | 0 | 36 | 0 / 6 |
| Held-out #1 (first run, before tuning) | 24 | 3 | 20 | 0 / 12 |
| Held-out #2 (first run, before tuning) | 20 | **2** | 14 (+4 "unsure") | 0 / 10 |

First-run misses were novel phrasings (crypto presale, "send it back" overpayment). Fixes made afterwards mean sets #1 and #2
are now dev sets, so the honest generalisation figure is the **first-run** row: roughly 1 in 10 novel scams slipped
through offline. That is why the pipeline never lets rules alone clear a message it can't read, and why the next step is a
third, fresh set (ideally real forwarded scams) and the live model.

## Repository layout
```
core/        channel-agnostic engine (domain / storage / ai / pipelines, see above)
web/         FastAPI app: main.py (routes), deps.py (profiles, rate limit, headers), cardimg.py, templates/, static/{css,js,img}
bot/         optional Telegram front-end (handlers.py is the tested logic)
data/        curated seed scams + legitimate examples
scripts/     verify_setup (Phase 0), eval_offline, eval_live, seed_demo
tests/       core/ web/ bot/ (pytest), data/ (labelled eval sets), e2e/ (real-browser click-through)
deploy/      Nebius VM: setup script, systemd unit, Caddyfile
```

## Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill NEBIUS_* and (optionally) TAVILY_API_KEY
python -m scripts.verify_setup --list   # Phase 0: confirm Nemotron id + base URL
uvicorn web.main:app --reload           # http://localhost:8000
pytest                                   # offline, deterministic
python -m scripts.seed_demo              # optional: believable mid-training state for the demo
```

## Safety & privacy
- Cautious verdicts: "looks safe" always carries "…but verify via an official channel"; any red flag downgrades a safe verdict.
- "I already paid" messages get victim support, not analysis, and are never stored.
- We store **tactics and an abstracted example**, not messages. Emails, phone numbers and link paths are scrubbed deterministically; with the AI configured the example is also rewritten without names. In offline mode, names in free text can survive scrubbing (limitation). No telemetry.
- Encouraging tone: a miss is always "here's the tell you missed". Content is victim-facing only.

## Status / limitations
Done: check, tactic model, drills (spot-the-trick, find-the-tell, what-to-do, safe-reply), score, flywheel, challenge + share card. Not yet: live Phase 0 verification, Nebius VM deploy, Telegram bot (stretch). Future: family dashboards, WhatsApp, voice/screenshot input, more languages. The single-user model means one DB per deployment.

## License
MIT

## Telegram bot (optional)
`pip install "python-telegram-bot>=21"`, set `TELEGRAM_BOT_TOKEN` (and `BAITPROOF_URL`), then `python -m bot.telegram_bot`.
Paste or forward a message to get the same gated verdict; `/score` shows your Baitproof score. The bot logic lives in
`bot/handlers.py` (no Telegram import, fully unit-tested); only the thin connector in `bot/telegram_bot.py` is untested
without a token. Set `BAITPROOF_MULTIUSER=1` so each chat gets its own anonymous profile.

## Deploy (Nebius VM)
`bash deploy/setup_vm.sh <repo-url>` installs the app behind Caddy (HTTPS) with a hardened systemd unit.
Public mode (`BAITPROOF_MULTIUSER=1`, set by the unit) gives every visitor their own anonymous profile database
(cookie, no accounts) so strangers never see each other's training; challenges are shared so the person you send
one to can open it. There is no CORS middleware (same origin only), a strict CSP, and a per-IP rate limit on the
routes that cost model calls (`BAITPROOF_RATE`, default 30/min). Inference still runs on Token Factory.
For the demo video, run locally without `BAITPROOF_MULTIUSER` and seed with `python -m scripts.seed_demo`.
