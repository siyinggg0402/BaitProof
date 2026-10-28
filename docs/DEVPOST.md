# Baitproof: Devpost submission draft

Track: **Personal AI**. Built on **Nebius Token Factory** with **NVIDIA Nemotron** (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` for checks, `nvidia/Nemotron-3.5-Super-VL` for screenshots) and **Tavily** for web lookups.

## Tagline
A free scam-defence coach for Singapore's families and friends. Paste a message, get a verdict and the giveaway, then train on the tricks that fool you. Already in all four official languages.

## Inspiration
Scams reach people in the chats they already use, in the language they already read. Singapore is multiracial, and its four official languages are English, Mandarin, Malay and Tamil, so a scam can arrive in any of them, and so can the person it fools: a parent, a grandparent, a friend. Detectors tell you once and forget you; enterprise training (Hoxhunt, KnowBe4) is sold to IT departments and drills synthetic scams. We wanted a coach for the people around you, **family and friends**: check a message, learn the one giveaway, and practise the tricks *you* fall for, with the real scams that reached your circle. Baitproof already works in all four official languages.

## What it does
- **Check**: paste or forward a message, **or a screenshot, or a voice note** (website or Telegram). You get a verdict, the one giveaway quoted from the message, what to do next, and a "How I decided" trace made of graded evidence, and a **Links panel** that says what each link is (a real company site, a look-alike, a known phishing site, or a short link and where it really goes).
- **Train**: short drills on the tricks you are weakest at, a game (Inbox Rush, Daily, Spot the Tell, a boss per trick), and a challenge link you can send to a parent or a friend, who plays it in two minutes with no account.
- **Finn, a fish who never bites**: a friendly scam-spotting mascot you can pick up and move around the website. He swims in when you arrive, reacts to your results and your game answers, and gives a safety tip when tapped. Baitproof, a fish that is *bait-proof*, and a face for a tool that is usually dry.
- **Telegram**: the same verdict in chat, a five-question `/quiz`, and `/challenge` to forward to a parent or a friend. Records on the website and in Telegram are one history. `/family` lets a trusted person get a short note when you meet a scam (never the message) and `/safeword` explains the family safe word.
- **Scam Road, a 3D game you play with friends**: a little car with your own character in the back window drives a three-lane road (three.js). Each sign shows a message; steer into *scam*, *check first* or *looks fine*. The server grades every lane, so scores cannot be forged. Make a profile with no email or password, add friends by code or invite link, and see a this-week and all-time leaderboard, plus flags on the road where each friend's best distance is.
- **A reason to come back**: a **Daily Road** that is the same for everyone, with **ghost cars** of friends' drives, cars and hats for Finn **earned by playing**, four road themes, sound made in the browser, a second game (**Link Hunt**, spot the fake address), **groups of family or friends** whose shared scams become gates in everyone's games, and optional **"Mei just passed you"** notifications.
- **Your character and your house**: build a character (skin tones, hairstyles including a tudung, outfits including a baju kurung, a kurta and a songkok) and spend the XP you earn on a 3D room: plants, furniture, wall art, pets and festival things sold only while their festival is on. Drag things around, turn them, put them away; your character walks between the furniture; friends can visit (read-only). The server checks every purchase and layout.
- **Race your friends, live**: up to four people drive the same 12 gates of Scam Road at the same moment and see each other's cars at their real pace; server-graded, so nobody can fake a score. The road also **dresses for the real festival** (Chinese New Year, Hari Raya, Deepavali, Mid-Autumn, Christmas, National Day), and a **family dashboard** shows, only with each person's consent, which scam tricks the group is least ready for.
- **Official help, one tap away**: scam and victim results show the official Singapore hotlines and reporting links (ScamShield 1799, the Anti-Scam Helpline 1800-722-6688, go.gov.sg/scamreport), tap-to-call on a phone, with the date they were checked.
- **All four official languages, and only yours**: English, 简体中文, 繁體中文, Bahasa Melayu and தமிழ் across the website, bot, practice and games. The explanation comes back in the language *you* read, whatever language the scam is in, and a game only ever shows messages in the site's language (a browser test checks this for every language).
- **Installable**: the website installs like an app and, on Android, appears in the Share sheet so a message from WhatsApp is checked in two taps.

## How we built it
- **Inference**: Nemotron Nano 30B-A3B on Nebius Token Factory, temperature 0, thinking off. A whole check costs about 0.03 US cents. Every model call, including the screenshot reader (Nemotron 3.5 Super VL), goes to Token Factory.
- **Tavily**: when a message names a company, Tavily looks up that company's real website and scam reports about the link. Directories and social sites are filtered out and a result must look like the company's own name before it counts; it is weak evidence and never decides alone. It shows in the "How I decided" panel.
- **Hosting**: one small Google Cloud server in Singapore runs the web app and the Telegram bot (FastAPI and SQLite, no model on it) behind Caddy with automatic HTTPS; it has nightly backups and cleanup.
- **The model proposes, deterministic gates decide.** Ingest and injection gate, victim triage, an intent diagnosis against a closed catalogue of 19 purposes, free local tools (look-alike domain check against a brand table, payment-rail check, offline phone-number rules, a local copy of a public phishing-site list), network tools behind an allow-list (domain age via RDAP with the certificate-transparency log as a second clock, DNS sanity, company verification through Wikidata, who registered a link's domain (WHOIS, compared with the company's own site), where a short link really goes), an **evidence ledger** (every finding is a graded record with a quote), a grounding gate (a quote must exist in the message, and a sentence the model writes may not add a web address or a number, or name a well-known Chinese company, that the message does not have), a precondition gate (no "fake link" without a link), an asymmetric arbiter ("safe" must be earned), a bounded confidence loop that asks a planner what to check next, a critic before anything is called safe, and an output gate.
- **Languages**: English, Chinese (Simplified and Traditional), Malay (with Indonesian) and Tamil all run the full pipeline, and Chinese, Malay and Tamil each have a rule pack of their own (links inside unspaced text, Simplified and Traditional from one pattern, Tamil's verb-final "don't", warnings that must not be read as requests); any other language goes to the model alone and is never called "safe".
- **Official warnings**: a short dated list of scam scripts that the Singapore Police Force, MAS and PDPC, among others, have named (`data/reference/entries.json`), matched exactly and shown in the result with who said it and when. A line can be added the day a new wave is announced, with no code change.
- **Privacy**: we keep tactics and an abstracted example, not messages; phone numbers, IDs, emails and link paths are scrubbed before anything is stored or sent; logs contain no message text.
- **Screenshots and voice**: a vision model on Token Factory reads a screenshot (and any QR code in it); voice notes are transcribed on the server with a small speech model or in the browser. What was read is shown back, and its links are made untappable.
- **Observability**: a JSONL event log, a health and cost dashboard, a live view of each gate as it runs.
- **Stack**: Python, FastAPI, SQLite, vanilla JS with a strict CSP, python-telegram-bot (updates handled concurrently), Playwright for the browser test, OpenCC character tables (Apache-2.0), the `phonenumbers` package and the Phishing.Database list (MIT). More than 1,600 automated tests.

## Challenges we ran into
- **A plain model over-flags.** One model call is a good scam catcher and a poor judge of genuine messages: it flagged 12 to 33% of genuine ones. The gates fix that, at the price of more "not sure".
- **Honest evaluation.** Our own test sets drift into the rules once you read the failures, so we kept a fresh split of real SMS we never tuned on as the headline number, reported the first reading before any tuning for the Chinese and Malay sets, and wrote down the negative results.
- **Languages are not translations.** Mandarin has no word boundaries and two scripts, links are written without spaces, Tamil's "don't" comes after the verb, and warnings ("请勿泄露验证码") contain the very words scams use.
- **Languages we cannot check.** A model-only "safe" let 1 to 2 scams in 40 through in five languages, so for languages without rules the pipeline now only ever says "not sure".
- **Prompts can hurt.** Adding Chinese examples and a "reply language" line made the model over-cautious (20 of 40 genuine cleared instead of 30); we measured it and removed them.
- **A bug after launch.** A friend saw a Spanish scam in the English game. There were two causes: a scam a visitor once checked in Spanish was dealt back to them, and our own reference bank holds a Spanish and a French example for the model. We fixed both, and added a real-browser test that plays every site language and fails if any foreign message appears.

## Accomplishments that we're proud of
- Real SMS never tuned on (100 scams, 100 genuine): 76 to 79 scams caught, **0 to 1 called safe** (none in the headline run, one in a later run), 0 to 2 false alarms, where a plain model flags 12 of 100 genuine messages (up to 33% on other sets). Read any figure as plus or minus 3.
- Chinese (hand-written holdout, 39 + 40): 36 of 39 scams caught, 0 called safe, 0 of 40 genuine flagged (a plain model flags 13).
- Malay, Indonesian and Tamil: 0 scams called safe in every set. Languages with no rules (model alone, never "safe"): 0 of 320 called safe in the first run, 2 of about 360 in the latest (an English spam the translation left in English, and a food promotion).
- Every verdict carries its evidence, and the model cannot talk the system out of hard evidence.
- The gates work with whichever model sits inside them: on the same 309 messages, genuine messages wrongly flagged fell from 44 to 0 with Nemotron Nano (and from 28 to 1 with Qwen3-30B-A3B), with no scam called safe.
- It is live, free, needs no account, and speaks all four of Singapore's official languages.

## What we learned
Measure everything and report the first reading. The most useful tests were the ones that made us look bad: the fresh split found two scams the rules called safe, and the multilingual run found a safety hole we would not have found with English alone. A model is best used as a proposer inside rules that can say no.

## What's next for BaitProof
A native-speaker review of the Malay and Tamil text, a WhatsApp bot (the chat app most people in Singapore already use), more Singlish and code-mixed messages in our test sets, and resuming a live race after a reload.

## Built with
Nebius Token Factory, NVIDIA Nemotron (Nano 30B for checks, Super VL for reading screenshots), Tavily, Python, FastAPI, SQLite, JavaScript, three.js, Web Audio, Web Push, Telegram Bot API, Caddy, Google Cloud, Playwright, pytest, OpenCC data, Pillow, Phishing.Database, libphonenumber.

## Built during the hackathon
The project was started on 2026-10-19, after the submission period opened (2026-08-26); there is no earlier version. Third-party material is small and credited: three.js (MIT, vendored), OpenCC character tables (Apache-2.0), the Phishing.Database list (MIT), the `phonenumbers` package, and public datasets used only for evaluation (never committed).

## Feedback on the Nebius and NVIDIA tools
Written from what we actually ran into; edit it to your own opinion before you submit.

**Nebius Token Factory**
- *Worked well:* the OpenAI-compatible endpoint meant changing a base URL and a key and nothing else. A whole check (two or three model calls of about 2 to 3 seconds each) costs about 0.03 US cents, which is what makes a free tool for everyone affordable. With Nemotron Nano at temperature 0, turning reasoning mode on cost about ten times the tokens and did not improve our verdicts.
- *Friction:* Token Factory and Nebius AI Cloud are separate consoles; with only a Token Factory account there is no Compute menu, so the rule "run on Token Factory or AI Cloud" left us unsure whether hosting a small web server elsewhere was acceptable. A line in the FAQ saying what Token Factory-only participants should host on would save people an afternoon. The API key is a very long token shown once; a one-line "test this key" example in the dashboard would help. During setup one request returned a 503 "Service Temporarily Unavailable" that cleared by itself, with no status link on the error page. Results are not perfectly repeatable at temperature 0 (the same sample gave 73 and 76 scams caught on two runs), so a note on determinism, or a seed option, would help anyone evaluating.

**NVIDIA Nemotron**
- *Strong at catching, weak at clearing:* a plain "is this a scam?" call caught 98 of 100 financial scams but called 12 to 33% of genuine messages scams. That is why the model only proposes and deterministic gates decide.
- *Compared with six other models* (same prompt, 389 messages in five languages, 27 October 2026): every model catches 96 to 99% of scams, but on genuine messages Nemotron 3 Nano wrongly flagged 51 of 195 (26%), against 62 (32%) for Gemma-3-27B, 31 (16%) for Qwen3-30B-A3B, and 7 (4%) for the larger Nemotron 3 Super, 6 for Qwen3-235B, 5 for gpt-oss-120b and 1 for DeepSeek-V4.1-Flash. Inside our gates the difference disappears (44 to 0 for Nano). We would love a Nano-sized model as well calibrated as Super.
- *Sensitive to the prompt:* adding Chinese examples and a reply-language line made it more suspicious (20 of 40 genuine messages cleared instead of 30), so we measured it and removed them.
- *Non-English:* for languages where we have no rules, a model-only "safe" let 1 to 2 of 40 scams through, so there we never let it say "safe".
- *Vision:* Nemotron 3.5 Super VL read the text from a screenshot of a fake parcel-fee message correctly, including the link; we still show what it read for the person to correct.

## Try it
- Demo: https://baitproof-sy.duckdns.org
- Code (MIT): https://github.com/siyinggg0402/Is-This-Legit
- Run it yourself: `README.md`, and `deploy/README.md` for a small Ubuntu server.
