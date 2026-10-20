# 🛡️ Baitproof

**A personal scam-defense coach for your family.** Forward a suspicious message and Baitproof tells you if it's a scam, points at the *one giveaway*, and adds that trick to your training. It learns which tricks *you* fall for, drills those, turns them into a game, and lets you send a "can you spot the scam?" challenge to your parents. It reads **English, Chinese (简体, 繁體 and mixed with English), Malay and Indonesian** with its own rules, and any other language through the model; the website, Telegram bot, practice and game speak English, 简体中文 and 繁體中文.

*Hoxhunt for protecting your parents, not your payroll.*

Built for the Nebius x NVIDIA Global AI Hackathon 2026, track **Personal AI**.

## What you can do
| | |
|---|---|
| **Check** | Paste or forward a message (web or Telegram). Get a verdict (scam / likely scam / not sure / looks fine), the one giveaway quoted from the message, what to do next, and a "How I decided" trace. |
| **Practice** | Short drills on the tricks *you* are weakest at: spot the trick, find the tell, what would you do, safe reply. Feeds a per-trick mastery model and a Baitproof score. |
| **Game** | Inbox Rush, Daily Challenge, Spot the Tell, Boss fights (one per trick) and *Your Inbox*, built from scams you actually received. XP, levels, combo, lives, streaks, badges. |
| **Records** | Everything you checked on the website **and in Telegram**, in one place, with the verdict and the giveaway. Link Telegram with a one-time code. Delete one record or all of them. |
| **Challenge family** | Send a link; your parent plays a few rounds with no account and you see how they did. Shareable result card. |
| **Your language** | A language switcher (English / 简体中文 / 繁體中文) on the website, `/lang` in Telegram. The explanation comes back in the language **you** read, whatever language the scam is in. |

## Why not a detector / ChatGPT / Hoxhunt?
- **Detectors** tell you once and forget you. Baitproof makes you harder to fool next time.
- **Enterprise trainers** (Hoxhunt, KnowBe4) are sold to IT departments and drill synthetic scams. Baitproof is for families and drills the **real scams reaching your circle**.
- **A plain LLM** is a good scam spotter and a poor judge of genuine messages: in our tests it called 12–33% of *genuine* messages scams (see Evaluation). Baitproof puts the model inside gates so it can raise suspicion but cannot invent evidence or clear a message it cannot read.

## Stack
- **Inference:** Nebius Token Factory (OpenAI-compatible, `https://api.tokenfactory.nebius.com/v1/`) with **NVIDIA Nemotron** `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, temperature 0, thinking mode off (`BAITPROOF_THINKING=1` to re-enable; it cost ~10x the tokens without improving verdicts). A whole Check costs well under a cent.
- **Web:** FastAPI + Jinja + vanilla JS. Strict CSP (no inline script or style), large type, high contrast, read-aloud. **State:** SQLite. **Optional:** Tavily (review-style web checks), Telegram bot.
- Without keys the app runs in **offline mode** using built-in rule checks, so it never crashes or gives a bare all-clear.

## How Check decides
```
ingest ─▶ victim ─▶ intent ─▶ local ─▶ evidence ledger ─▶ arbiter ─▶ confidence ─▶ critic ─▶ output ─▶ flywheel
 gate      triage    diagnosis  tools   rules + tools +    asymmetric   loop         before     gate       gate
 (injection,         what is it          intent + model     decision     (planner,    "safe"
 entities)           asking me           (quotes must       table        gated tools,
                     to DO?              exist; tactics                  re-analysis)
                                         need preconditions)
```
The model proposes; deterministic gates decide.

- **Intent diagnosis against a closed catalogue** (`core/domain/intents.py`, 19 purposes such as *one-time code*, *delivery update*, *payment request*, *urgent account warning*). Rules and the model each pick a purpose; the model must choose from the catalogue, and its pick is validated against what the message actually asks for. Only three purposes can ever be cleared as safe, and only when strict conditions hold (e.g. a one-time code with no link and no request to share it). A risky purpose is never cleared.
- **Evidence ledger.** Every finding is an `Evidence` record: kind (rule / intent / tool / model), source, supports scam / safe / neutral, strength, and the quote it rests on. Model evidence counts half. The UI "How I decided" panel is this ledger.
- **Grounding and precondition gates.** A red flag whose quote is not in the message is dropped; a tactic needs its precondition to exist (no "fake link" without a link, no "asks for money" without an ask).
- **Arbiter.** Strong independent evidence means scam. Safe must be earned: no risky purpose, no unresolved links, a second look agreeing, and evidence that is not just the model. Model-only suspicion needs two consistent looks before it becomes "likely scam". Otherwise the honest answer is "not sure".
- **Confidence loop.** When the verdict depends on the model, a bounded loop (max 3 rounds, 10 model calls, 25 s) asks a planner which open question matters most, runs the allowed tools in parallel, and re-analyses, stopping as soon as the verdict is settled.
- **Tools** behind a gate (allow-list, arguments must come from the message, public hostnames only, budget, timeouts, never contacts the scammer's server): official-domain check against a 70-brand table with look-alike detection, payment-rail check, phone check, domain age (RDAP), DNS sanity check, **company verification through Wikidata** (no key needed), and Tavily brand lookup when a key is set.
- **Critic** looks again, with the verified facts, before anything is called safe.
- **Flywheel gate.** Only confident scams with independent evidence enter the training library, and only as tactics plus an abstracted, scrubbed example.

### Observability
Every check writes one JSON line to `logs/` (stages, tools, latency, tokens, cost; **no message text**, only a salted hash and length). `/admin` (set `BAITPROOF_ADMIN_TOKEN`) shows health, metrics, recent checks and user feedback ("was this right?"). `python -m scripts.ops.logs_report` does the same in the terminal. A crash guard turns any internal error into a cautious "not sure". The Check page streams the stages live.

### Optional: few-shot retrieval
`core/ai/fewshot.py` can put the four most similar labelled examples from `data/fewshot/bank.json` into the prompt (`BAITPROOF_FEWSHOT=1`). Off by default; see Evaluation for what it did.

## Languages
| Message language | How it is checked |
|---|---|
| English | The full pipeline: rules, intent diagnosis, tools, evidence ledger, model, gates. |
| Chinese: Simplified, Traditional, or mixed with English | The same pipeline with a Chinese rule pack (`core/lang/zh.py`): deadlines and threats, claimed authorities, asks (pay, share a code, install, scan), 17 scam scripts (parcel fee, bank freeze, impersonated police, brush-order jobs, romance to investment, fake customer-service refund, boss and family emergencies, prizes, loans, social security, traffic fines, tickets, rentals ...), Chinese brands and official domains, links found inside unspaced Chinese text, and warnings such as "请勿泄露验证码" or public anti-fraud notices that must not be read as scams. Each rule is written once in Simplified and also matches Traditional. |
| Malay and Indonesian | The same, with a Malay/Indonesian pack (`core/lang/ms.py`): PDRM, LHDN, Kastam, SPRM, JPJ and bank impersonation, TAC/OTP read-outs, parcel and customs fees, "new number" family emergencies, task jobs and investment promises. |
| Anything else (Japanese, Korean, Hindi, Arabic, Spanish, French ...) | The model alone, inside the same gates. Because no independent rule can check these, Baitproof **never says "looks safe"** for them, only "not sure" (measured below: without this, 1 to 2 scams in 40 were called safe). |

**You choose the language of the answer**, not the message: a Chinese-speaking relative can check an English phishing email and read the explanation in Chinese, and the other way round. The website remembers it (cookie, else the browser's language), Telegram uses `/lang en|zh|zh-Hant` (else Telegram's language). Verdict, giveaway, next step, every piece of evidence and the "How I decided" trace are translated; Traditional is derived from the Simplified text with OpenCC's character table (see [NOTICE](NOTICE)) plus a few Taiwan-style words, so wording is correct but not hand-polished. The practice, game and challenge messages for Chinese come from their own bank of 47 hand-written messages.

## Evaluation
`python -m scripts.eval.offline` (rules, free, false-SAFE must be 0), `scripts.eval.live` (live model, token-capped), `compare` (the hard sets against a plain model call), `prompt_lab`, `real` (real datasets, see `data/external/README.md`) and `multilingual`; the data is downloaded by `scripts.data.fetch`, never committed. [scripts/README.md](scripts/README.md) lists every script and what it costs.

**What we optimise for:** never tell someone a scam is safe, and don't cry wolf on genuine messages. When unsure, the honest answer is "not sure, check with someone you trust". We compare against the obvious baseline, *one plain call to the same model* ("is this a scam?").

**1. Fresh real SMS the system was never tuned on.** DIFrauD SMS *train* split (5,217 real messages), 100 scams + 100 genuine, random sample, final build:

| System | Scams caught | "Not sure" | Called safe | Genuine cleared | "Not sure" | False alarms |
|---|---|---|---|---|---|---|
| **Baitproof pipeline** (default) | **76 / 100** | 24 | **0** | 58 / 100 | 40 | **2** |
| Pipeline + few-shot retrieval | 80 / 100 | 20 | 0 | 38 / 100 | 60 | 2 |
| Rules only, offline, all 1,019 scams + 4,198 genuine | 617 / 1,019 (61%) | 401 | 1, now 0 (note) | 1 | 4,142 | 55 (1.3%) |

Cost: about $0.05 per 200 messages (roughly $0.0003 per check). Runs are not perfectly repeatable even at temperature 0 (the same sample gave 73 and 76 caught on two runs), so read ±3 on any figure.
Note: the first rules-only pass found **one** scam called safe (a premium-content SMS dressed as an order update with a split-up web address). It is fixed and has a regression test; the rescan is 0 of 1,019. Few-shot raised catches by 7 but cleared 18 fewer genuine messages for no fewer false alarms, so it stays **off by default**.

**2. Against one plain model call** (hard sets written by us; sets 1 and 2 are tuning sets, set 3 was a clean holdout until one opener rule was added after it exposed a gap, so treat all three as development sets):

| Set | Plain model: scams caught / genuine false alarms | Baitproof: scams caught / false alarms | Called safe |
|---|---|---|---|
| Hard set 1 (24+24) | 22 / 24, 8 of 24 genuine flagged | 17 / 24, 0 flagged | 0 |
| Hard set 2 (20+20) | 20 / 20, 4 of 20 flagged | 20 / 20, 1 flagged | 0 |
| Hard set 3 (20+20) | 19 / 20, 5 of 20 flagged | 12 / 20, 0 flagged | 0 |

Earlier build, real English financial messages (Mendeley, 100 scams + 70 genuine): the plain model caught 98 / 100 but flagged **23 of 70 genuine notices (33%)** as scams; the pipeline caught 56 / 100, said "not sure" on 42, and flagged 2 of 70. Not re-run on the final build.

**Honest reading:** a single model call is the better scam *catcher* and a poor judge of genuine messages; the pipeline gives up some catches (as "not sure", never as "safe") to stop calling a parent's real bank text a scam. That is the right trade for a family tool, but it means roughly one in four scams currently gets "not sure" rather than a firm verdict.

**Data caveats.** Datasets are older (2003-2012 UK/Singapore/India SMS) and English; "spam" is not always "scam"; some labelled-genuine finance messages were volunteer-written and look templated. Our own seed and hard sets are partly contaminated because rules were written after seeing failure categories, which is why the fresh train split is the headline number. None of the third-party data is committed.

## Telegram
```bash
pip install "python-telegram-bot>=21"
# .env: TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_USERNAME, BAITPROOF_URL
python -m bot.telegram_bot
```
Paste or forward a message to the bot for the same gated verdict. Commands: `/start`, `/link CODE`, `/unlink`, `/history`, `/score`, `/lang en|zh|zh-Hant`, `/help`.
**Link it to the web:** open **Records**, press *Connect Telegram*, and send the 6-character code (valid once, 10 minutes) to the bot. From then on every check made in Telegram appears in your web Records and trains the same profile. Anything you check in Telegram is saved to Records and the bot tells you so. The logic is in `bot/handlers.py` (no Telegram import, unit-tested); only the thin connector `bot/telegram_bot.py` needs a token to run.

## Game mode
`core/game/` is the engine, `web/routes/game.py` the API. Answers are graded **on the server** (so the page cannot be used to peek): *scam*, *looks fine* or *check first*, with partial credit for "check first". Spot the Tell asks you to highlight the giveaway and scores recall and precision (selecting the whole message does not count). Rounds update the same per-trick mastery model that drives Practice. The pool is the curated seed bank plus the authored bank plus scams you have checked yourself.

## Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt     # requirements.txt is the runtime only
cp .env.example .env                    # fill NEBIUS_API_KEY (never commit it; .env is gitignored)
python -m scripts.ops.verify_setup --list   # confirm the Nemotron model id and base URL
uvicorn web.main:app --reload           # http://localhost:8000
pytest                                   # offline, deterministic, never calls the API
python -m tests.e2e.browser              # real-browser click-through (needs Chrome + playwright)
python -m scripts.data.seed_demo              # optional: believable mid-training state for the demo
```
The share card renders Chinese when a CJK font is installed (`fonts-noto-cjk` on Linux, which `deploy/setup_vm.sh` installs) and falls back to the English card otherwise.
All settings are listed, with defaults, in [.env.example](.env.example).

## Safety & privacy
- Cautious verdicts: "looks safe" always carries "…but verify via an official channel"; any red flag downgrades a safe verdict.
- "I already paid" messages get victim support, not analysis, and are never stored.
- We store **tactics and an abstracted example**, not messages. Emails, phone numbers (including mainland-China mobiles), resident ID numbers, card numbers and link paths are scrubbed deterministically before anything is stored or sent to a model; with the AI configured the example is also rewritten without names. In offline mode names in free text can survive scrubbing (limitation).
- **Records** keep the verdict and giveaway; the 120-character preview of the message is redacted, optional (`BAITPROOF_STORE_PREVIEW`, switchable per profile) and deletable per record or all at once.
- Logs contain no message text. No telemetry. Third-party datasets are never committed.
- Encouraging tone: a miss is always "here's the tell you missed". Content is victim-facing only.

## Repository layout
```
core/domain/     tactics.py (12-tactic vocabulary), intents.py (19-purpose catalogue), schemas.py, privacy.py
core/lang/       text.py (language detection, Simplified/Traditional-agnostic patterns), zh.py + ms.py (Chinese and Malay/Indonesian rule packs),
                 i18n.py + i18n_ui.py + i18n_bot.py (English text -> Simplified; Traditional is derived), data/ (OpenCC character tables)
core/storage/    db.py, library.py, model.py (personal model + score), history.py (records), links.py (Telegram link codes)
core/ai/         llm.py (Nebius client), prompts.py, verify.py (Tavily), fewshot.py
core/pipelines/  train.py, challenge.py, check/ (the gated pipeline: engine, gates, evidence, intent, scenarios, tools, planner, preconditions)
core/game/       pool.py, state.py (XP, levels, badges), engine.py (rounds, grading)
core/obs/        run, logger (JSONL), metrics, health
web/             main.py (app setup), pages.py (templates), ui.py (translation helpers), deps.py (profiles, rate limit, headers),
                 routes/ (check, records, practice, game, language, admin), templates/, static/{css,js,img}
bot/             Telegram front-end (handlers.py is the tested logic)
data/            seeds/ (curated scams + genuine messages, en and zh), fewshot/ (reference bank), external/ (downloaded, ignored)
scripts/         eval/ (offline, live, compare, real, multilingual, prompt_lab), data/ (fetch, seed_demo), ops/ (verify_setup, logs_report), common.py
tests/           core/ (by area: check, lang, game, pipelines, storage, obs, ai), web/, bot/ (pytest); data/{en,zh,ms}/ (labelled sets); e2e/ (real-browser)
deploy/          Nebius VM: setup script, systemd unit, Caddyfile
```

## Deploy (Nebius VM)
`bash deploy/setup_vm.sh <repo-url>` installs the app behind Caddy (HTTPS) with a hardened systemd unit.
Public mode (`BAITPROOF_MULTIUSER=1`, set by the unit) gives every visitor their own anonymous profile database
(cookie, no accounts) so strangers never see each other's training or records; challenges and Telegram link codes are shared so the person you send
one to can open it. There is no CORS middleware (same origin only), a strict CSP, a per-IP rate limit on the
routes that cost model calls (`BAITPROOF_RATE`, default 30/min) and a login rate limit on `/admin`. Inference still runs on Token Factory.
For the demo video, run locally without `BAITPROOF_MULTIUSER` and seed with `python -m scripts.data.seed_demo`.

## Limitations
- The deploy files have not been exercised on a real VM yet.
- The Telegram connector has only been tested through its handlers, not against the live Telegram API.
- Short or context-free messages ("Hi, is this Amy?") are honestly answered "not sure"; the pipeline prefers that to guessing.
- Public datasets are older, mostly UK/Singapore/India SMS and English financial notices; "spam" is not always "scam". Tavily review checks are untested without a key.
- The Chinese and Malay/Indonesian test sets and seed messages are hand-written by us from common real scam scripts, not captured messages, and the only large multilingual dataset we found is machine-translated SMS. Treat those numbers as a development signal, not a benchmark.
- Malay/Indonesian are explained in English or Chinese (the interface languages). Traditional Chinese text is auto-converted from Simplified, so some wording is mainland-style.
- Future: family dashboards, WhatsApp, voice and screenshot input, a Malay/Tamil interface, more rule packs (Japanese, Korean, Hindi).

## License
MIT
