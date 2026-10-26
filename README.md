# Baitproof

<img src="web/static/img/finn.png" alt="Finn, the Baitproof fish" width="150" align="right">

**A personal scam-defense coach for your family.** Forward a suspicious message and Baitproof tells you if it's a scam, points at the *one giveaway*, and adds that trick to your training. It learns which tricks *you* fall for, drills those, and turns them into games you can play with your family and friends.

**Try it: https://baitproof-sy.duckdns.org** (free, no account). English, 简体中文, 繁體中文, Bahasa Melayu and தமிழ். MIT licence.

## Hackathon requirements
Nebius x NVIDIA Global AI Hackathon 2026, track **Personal AI**.

| Requirement | How and where we meet it |
|---|---|
| Built and run on **Nebius Token Factory** | Every model call goes to Token Factory's OpenAI-compatible endpoint (`core/ai/llm.py`, `.env.example`). The web app and Telegram bot are a small FastAPI and SQLite server (Google Cloud, Singapore) with no model on it. |
| At least one **NVIDIA open model** | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` runs every check (temperature 0, thinking off, about $0.0003 per check). `nvidia/Nemotron-3.5-Super-VL` reads screenshots. |
| **Tavily** (extra prize) | `core/ai/verify.py`: when a message names a company, it looks up the company's real website and scam reports about the link. Shown in "How I decided"; weak evidence that never decides alone. |
| Working **demo** | https://baitproof-sy.duckdns.org |
| Public **repository**, open licence, README | This repository, MIT ([LICENSE](LICENSE)); how to run it is under [Setup](#setup). |
| **Video** (YouTube, under 3 minutes) | Linked on the Devpost page. |

## What it does
- **Check.** Paste or forward a message, a screenshot or a voice note (website or Telegram). You get a verdict (scam / likely scam / not sure / looks fine), the one giveaway quoted from the message, what to do next, a **Links** panel (real site, look-alike, short link expanded safely, new or non-existent site), the official Singapore and Malaysia help lines, and a "How I decided" trace of graded evidence.
- **Train.** Drills on the tricks *you* are weakest at, and games: **Scam Road** (a 3D drive where each lane is an answer, graded on the server; Daily Road, ghost cars, live races), Inbox Rush, Daily Challenge, Link Hunt, Spot the Tell and boss fights. The XP you earn buys a character and a 3D house.
- **Family and friends.** Profiles with no email or password, friends by code or invite link and a leaderboard, family groups whose shared (redacted) scams become gates in everyone's games, a family dashboard, and a "can you spot the scam?" challenge link for a parent.
- **Telegram bot.** The same verdicts, `/quiz`, voice notes, screenshots and `/challenge`, linked to your web records with one tap.
- **Finn**, a scam-spotting fish who swims around the site. The website installs like an app and, on Android, appears in the Share sheet.

## How Check decides
```
ingest ─▶ victim ─▶ intent ─▶ local ─▶ evidence ledger ─▶ arbiter ─▶ confidence ─▶ critic ─▶ output ─▶ flywheel
 gate      triage    diagnosis  tools   rules + tools +    asymmetric   loop         before     gate       gate
                                        intent + model     decision                  "safe"
```
The model proposes; deterministic gates decide.
- **Intent diagnosis** against a closed catalogue of 19 purposes (`core/domain/intents.py`). The model must choose from it and its pick is validated. Only three purposes can ever be cleared as safe, and only under strict conditions.
- **Evidence ledger.** Every finding is a record: kind (rule, intent, tool, reference, model), source, direction, strength and the quote it rests on. Model evidence counts half. "How I decided" is this ledger.
- **Grounding gates.** A red flag whose quote is not in the message is dropped; a tactic needs its precondition (no "fake link" without a link).
- **Arbiter.** Strong independent evidence means scam. Safe must be earned: no risky purpose, no unresolved link, a second look agreeing, and evidence that is not just the model. Model-only suspicion needs two consistent looks to become "likely scam". Otherwise the answer is "not sure".
- **Tools** behind an allow-list (public hostnames only, a budget, timeouts, never the scammer's server): look-alike domain check, payment rails, offline phone rules, a local copy of the public Phishing.Database list, domain age and certificate history, DNS, Wikidata and **Tavily** company lookups, safe short-link expansion, and a short dated list of scripts that official bodies have named (`data/reference/entries.json`).
- **Confidence loop** (at most 3 rounds, 10 model calls, 25 seconds), then a **critic** before anything is called safe, then a **flywheel gate**: only confident scams with independent evidence, in a supported language, are kept for training, as tactics plus a scrubbed example.

Each check writes one JSON line with no message text; `/admin` (set `BAITPROOF_ADMIN_TOKEN`) shows health, spend and recent checks. Without keys the app runs in offline mode on its built-in rules, so it never crashes or gives a bare all-clear.

## Languages
| Message language | How it is checked |
|---|---|
| English | The full pipeline. |
| Chinese (Simplified, Traditional or mixed with English) | The same, plus a Chinese rule pack (`core/lang/zh.py`): 17 scam scripts, brands and official domains, links inside unspaced text, and warnings that must not be read as scams. |
| Malay and Indonesian | The same, plus `core/lang/ms.py`. |
| Tamil | The same, plus `core/lang/ta.py`, written for Tamil script. |
| Anything else | The model alone, inside the same gates. Baitproof **never says "looks safe"** for these, never keeps them for training, and never shows them in a game. |

The language you *see* is always the site's language (the header menu), never the language of a message: a game only shows messages written in the site's language, and a browser test checks this for every language.

## Results
Our own test sets, with one plain model call as the baseline. Full tables, first readings and negative results are in [docs/EVALUATION.md](docs/EVALUATION.md).

| Set (scams + genuine) | Plain model: scams caught / genuine wrongly flagged | Baitproof: scams caught / called safe / genuine wrongly flagged |
|---|---|---|
| Real English SMS, never tuned on (100 + 100) | 94 / 12 | 76 to 79 / **0 to 1** / 0 to 2 (two runs) |
| Chinese, held out (39 + 40) | 38 / 13 | 36 / **0** / 0 |
| Malay (20 + 20) | 20 / 6 | 20 / **0** / 0 |
| Indonesian, fresh (20 + 20) | 20 / 3 | 20 / **0** / 0 |
| Tamil, held out (25 + 25) | 25 / 14 to 17 | 25 / **0** / 0 |

A single model call is the better scam *catcher* and a poor judge of genuine messages (it flagged 12 to 33% of them). The gates give up some catches (as "not sure", never as "safe") so a parent's real bank text is not called a scam. Runs move by one or two messages, so read any figure as plus or minus 3. The Chinese, Malay, Indonesian and Tamil sets are written by us from common scam scripts: a development signal, not a benchmark.

## Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt     # requirements.txt is the runtime only
cp .env.example .env                    # fill NEBIUS_API_KEY (never commit it; .env is gitignored)
python -m scripts.ops.verify_setup --list   # confirm the Nemotron model id and base URL
uvicorn web.main:app --reload           # http://localhost:8000
pytest                                   # offline, deterministic, never calls the API
python -m tests.e2e.browser              # real-browser click-through (needs Chrome + playwright)
python -m tests.e2e.language_scope       # real browser: every site language shows only its own language
python -m scripts.data.seed_demo         # optional: a believable mid-training state
pip install "python-telegram-bot>=21" && python -m bot.telegram_bot   # optional bot (TELEGRAM_BOT_TOKEN in .env)
pip install -r requirements-extras.txt   # optional: voice notes (faster-whisper), QR codes, notifications
```
Every setting is listed, with its default, in [.env.example](.env.example). [scripts/README.md](scripts/README.md) lists the evaluation and operations scripts.

## Deploy
The live demo runs on one small Google Cloud server in Singapore; every model call goes to Nebius Token Factory. Any Ubuntu 24.04 server works: `bash deploy/setup_vm.sh <repo-url> [domain]` installs the app behind Caddy (automatic HTTPS) with hardened systemd units, a nightly backup and cleanup. Steps in [deploy/README.md](deploy/README.md).

## Safety and privacy
- We keep **tactics and an abstracted example, not messages**. Emails, phone numbers, ID and card numbers and link paths are scrubbed before anything is stored or sent to a model. Logs contain no message text; there is no telemetry.
- A **screenshot** goes unmodified to the vision model on Nebius (names and numbers in it cannot be scrubbed first); EXIF data is stripped and the picture is never stored. Telegram **voice notes** are transcribed on our own server and never sent anywhere.
- Only a known **URL shortener** is ever contacted (one HEAD request, to read where it points), never the destination. Of the other network tools, only a domain name is sent, never the message.
- "Looks safe" always carries "...but verify". "I already paid" messages get victim support, not analysis, and are never stored.
- Accounts hold a nickname, a character, a hash of the sign-in key and friendships; never an email or a password.
- Strict CSP (no inline script or style), no CORS, a per-IP rate limit on routes that cost model calls, a login limit on `/admin`.

## Layout
```
core/      domain (tactics, intents, privacy), lang (rule packs, translations), ai (Nebius client, prompts, Tavily), pipelines/check (the gated pipeline),
           game, storage, inputs (screenshots, voice), obs (logs, metrics)
web/       FastAPI app: routes, templates, static (css, js, vendored three.js)
bot/       Telegram front-end
data/      seeds (curated scams and genuine messages in en, zh, ms, ta), reference (dated official warnings), fewshot, external (downloaded, ignored)
scripts/   eval, data, ops
tests/     pytest (core, web, bot), labelled data sets, e2e (real browser)
deploy/    setup script, systemd units, Caddyfile
docs/      EVALUATION.md (full measurements and limitations), DEVPOST.md (submission text), TAMIL.md
```

## Limitations
- About one in four scams gets "not sure" rather than a firm verdict: the pipeline prefers that to guessing, and never answers "safe" without independent evidence.
- The Malay, Indonesian and Tamil interface text and rules were written by us and have **not been reviewed by a native speaker**.
- The demo is one small server: a nightly backup on the same disk is the only copy, and the demo's data resets if the server is rebuilt.
- The Telegram connector is tested through its handlers; its link to the live Telegram API is checked by hand.
- Scam Road needs WebGL; notifications need HTTPS and the site's push keys; iOS has no share target.
- The official help-line numbers were checked in October 2026; recheck `core/domain/helplines.py` before relying on it.

More in [docs/EVALUATION.md](docs/EVALUATION.md#limitations).

## License
MIT. Third-party notices (OpenCC character tables, three.js) are in [NOTICE](NOTICE).
