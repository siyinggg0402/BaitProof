# Baitproof: Devpost submission draft

Fill the bracketed items (demo URL, video URL, final numbers) before posting. Track: **Personal AI**. Built on **Nebius Token Factory** with **NVIDIA Nemotron** (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`).

## Tagline
A scam-defence coach for your family: it doesn't just tell you what's a scam, it makes you and your parents harder to fool next time.

## Inspiration
Scams reach families in the chats they already use, in the languages they already speak. Detectors tell you once and forget you; enterprise training (Hoxhunt, KnowBe4) is sold to IT departments and drills synthetic scams. We wanted the family version: check a message, learn the one giveaway, and practise the tricks *you* fall for, with the real scams that reached your circle. In Singapore and Malaysia that has to work in English, Chinese and Malay.

## What it does
- **Check**: paste or forward a message, **or a screenshot, or a voice note** (website or Telegram). You get a verdict, the one giveaway quoted from the message, what to do next, and a "How I decided" trace made of graded evidence, and a **Links panel** that says what each link is (a real company site, a look-alike, a known phishing site, or a short link and where it really goes).
- **Train**: short drills on the tricks you are weakest at, a game (Inbox Rush, Daily, Spot the Tell, a boss per trick), and a family challenge link your parent can play in two minutes with no account.
- **Finn, a fish who never bites**: a friendly scam-spotting mascot you can pick up and move around the website. He swims in when you arrive, reacts to your results and your game answers, and gives a safety tip when tapped. Baitproof, a fish that is *bait-proof*, and a face for a tool that is usually dry.
- **Telegram**: the same verdict in chat, a five-question `/quiz`, and `/challenge` to forward to a parent. Records on the website and in Telegram are one history. `/family` lets a trusted person get a short note when you meet a scam (never the message) and `/safeword` explains the family safe word.
- **Scam Road, a 3D game you play with friends**: a little car with your own character in the back window drives a three-lane road (three.js). Each sign shows a message; steer into *scam*, *check first* or *looks fine*. The server grades every lane, so scores cannot be forged. Make a profile with no email or password, add friends by code or invite link, and see a this-week and all-time leaderboard, plus flags on the road where each friend's best distance is.
- **A reason to come back**: a **Daily Road** that is the same for everyone, with **ghost cars** of friends' drives, cars and hats for Finn **earned by playing**, four road themes, sound made in the browser, a second game (**Link Hunt**, spot the fake address), **family groups** whose shared scams become gates in the kids' games, and optional **"Mei just passed you"** notifications.
- **Your character and your house**: build a character (skin tones, hairstyles including a tudung, baju kurung, songkok) and spend the XP you earn on a 3D room: plants, furniture, wall art, pets and festival things sold only while their festival is on. Drag things around, turn them, put them away; your character walks between the furniture; friends can visit (read-only). The server checks every purchase and layout.
- **Race your friends, live**: up to four people drive the same 12 gates of Scam Road at the same moment and see each other's cars at their real pace; server-graded, so nobody can fake a score. The road also **dresses for the real festival** (Chinese New Year, Hari Raya, Deepavali, Mid-Autumn, Christmas, National Day, Merdeka), and a **family dashboard** shows, only with each person's consent, which scam tricks the family is least ready for.
- **Official help, one tap away**: scam and victim results show the Singapore and Malaysia hotlines and reporting links (ScamShield 1799, NSRC 997, Semak Mule, go.gov.sg/scamreport), tap-to-call on a phone, with the date they were checked.
- **Installable, and in your language**: the website installs like an app and, on Android, appears in the Share sheet so a message from WhatsApp is checked in two taps. The interface, answers, help lines and practice messages come in English, Bahasa Melayu, தமிழ் (Tamil), 简体中文 and 繁體中文.
- **Your language**: English, 简体中文 and 繁體中文 across the website, bot, practice and game. The explanation comes back in the language *you* read, whatever language the scam is in.

## How we built it
- **Inference**: Nemotron Nano 30B-A3B on Nebius Token Factory, temperature 0, thinking off. A whole check costs well under a cent.
- **The model proposes, deterministic gates decide.** Ingest and injection gate, victim triage, an intent diagnosis against a closed catalogue of 19 purposes, free local tools (look-alike domain check against a brand table, payment-rail check, offline phone-number rules, a local copy of a public phishing-site list), network tools behind an allow-list (domain age via RDAP with the certificate-transparency log as a second clock, DNS sanity, company verification through Wikidata, who registered a link's domain (WHOIS, compared with the company's own site), where a short link really goes), an **evidence ledger** (every finding is a graded record with a quote), a grounding gate (a quote must exist in the message), a precondition gate (no "fake link" without a link), an asymmetric arbiter ("safe" must be earned), a bounded confidence loop that asks a planner what to check next, a critic before anything is called safe, and an output gate.
- **Languages**: Chinese, Malay/Indonesian and Tamil rule packs (links inside unspaced text, Simplified and Traditional from one pattern, Tamil's verb-final "don't", warnings that must not be read as requests); any other language goes to the model alone and is never called "safe".
- **Official warnings**: a short dated list of scam scripts that police, MAS, PDPC, OJK and India's cyber-crime centre have named (`data/reference/entries.json`), matched exactly and shown in the result with who said it and when. A line can be added the day a new wave is announced, with no code change.
- **Privacy**: we keep tactics and an abstracted example, not messages; phone numbers, IDs, emails and link paths are scrubbed before anything is stored or sent; logs contain no message text.
- **Screenshots and voice**: a vision model on Token Factory reads a screenshot (and any QR code in it); voice notes are transcribed on the server with a small speech model or in the browser. What was read is shown back, and its links are made untappable.
- **Observability**: a JSONL event log, a health and cost dashboard, a live view of each gate as it runs.
- **Stack**: Python, FastAPI, SQLite, vanilla JS with a strict CSP, python-telegram-bot (updates handled concurrently), Playwright for the browser test, OpenCC character tables (Apache-2.0), the `phonenumbers` package and the Phishing.Database list (MIT).

## Challenges
- **A plain model over-flags.** One model call is a good scam catcher and a poor judge of genuine messages: it flagged 12 to 33% of genuine ones. The gates fix that, at the price of more "not sure".
- **Honest evaluation.** Our own test sets drift into the rules once you read the failures, so we kept a fresh split of real SMS we never tuned on as the headline number, reported the first reading before any tuning for the Chinese and Malay sets, and wrote down the negative results.
- **Chinese is not English with different words.** No word boundaries, two scripts, links written without spaces, and warnings ("请勿泄露验证码") that contain the very words scams use.
- **Languages we cannot check.** A model-only "safe" let 1 to 2 scams in 40 through in five languages, so for languages without rules the pipeline now only ever says "not sure".
- **Prompts can hurt.** Adding Chinese examples and a "reply language" line made the model over-cautious (20 of 40 genuine cleared instead of 30); we measured it and removed them.

## Accomplishments
[Fill from the README evaluation section when final.]
- Real SMS never tuned on (100 scams, 100 genuine): [76] scams caught, **0 called safe**, [2] false alarms, where a plain model flags [12 to 33%] of genuine messages.
- Chinese (hand-written holdout, 39 + 40): 36 of 39 scams caught, 0 called safe, 0 of 40 genuine flagged (a plain model flags 13).
- Malay and Indonesian: 0 scams called safe on 35 scams; other languages: 0 of 320 scams called safe.
- Every verdict carries its evidence, and the model cannot talk the system out of hard evidence.

## What we learned
Measure everything and report the first reading. The most useful tests were the ones that made us look bad: the fresh split found two scams the rules called safe, and the multilingual run found a safety hole we would not have found with English alone.

## What's next
Resuming a race after a reload, spectators, a WhatsApp bot, a native-speaker review of the Malay and Tamil text, rule packs for Japanese, Korean and Hindi, and an embedding-based retrieval of similar scams.

## Built with
Nebius Token Factory, NVIDIA Nemotron (Nano 30B for checks, Super VL for reading screenshots), Python, FastAPI, SQLite, three.js, Web Audio, Web Push, Telegram Bot API, Playwright, OpenCC data, Phishing.Database, libphonenumber.

## Try it
- Demo: [URL]
- Code (MIT): [repo URL]
- Video: [URL]
- Run it yourself: `README.md`, and `deploy/README.md` for a VM.
