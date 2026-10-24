# 🛡️ Baitproof

<img src="web/static/img/finn.png" alt="Finn, the Baitproof fish" width="150" align="right">

**A personal scam-defense coach for your family.** Forward a suspicious message and Baitproof tells you if it's a scam, points at the *one giveaway*, and adds that trick to your training. It learns which tricks *you* fall for, drills those, turns them into a game, and lets you send a "can you spot the scam?" challenge to your parents. It reads **English, Chinese (简体, 繁體 and mixed with English), Malay and Indonesian** with its own rules, and any other language through the model; the website, Telegram bot, practice and game speak English, 简体中文 and 繁體中文.

*Hoxhunt for protecting your parents, not your payroll.*

Built for the Nebius x NVIDIA Global AI Hackathon 2026, track **Personal AI**.

## What you can do
| | |
|---|---|
| **Check** | Paste or forward a message (web or Telegram). Get a verdict (scam / likely scam / not sure / looks fine), the one giveaway quoted from the message, what to do next, and a "How I decided" trace. |
| **Train** | Short drills on the tricks *you* are weakest at: spot the trick, find the tell, what would you do, safe reply. Feeds a per-trick mastery model and a Baitproof score. The tab opens on **your house** (a live 3D preview of your room, your level and streak, and the one button that opens it), then the games (Scam Road as the big tile, Inbox Rush and the Daily Challenge beside it, Link Hunt, Spot the Tell and Boss fights as plain rows), then quick practice and your resilience map. *Your Inbox* is built from scams you actually received. XP, levels, combo, lives, streaks, badges. |
| **Records** | Everything you checked on the website **and in Telegram**, in one place, with the verdict and the giveaway. Connect Telegram with **one tap** on Records or My profile (the page opens the bot with a one-time code in the link, you press Start in Telegram and the page notices; a typed `/link CODE` still works). A tapped link never moves a chat that already belongs to another profile, and the bot names the profile it connected to, with `/unlink` to undo. Delete one record or all of them. |
| **Screenshot, voice, links** | Send a **screenshot** (website: button, drag-and-drop or paste; Telegram: just send the photo) and a vision model reads the message, which is put in the text box so you can see and correct it before it is checked. Speak instead (browser speech recognition on the website, a local speech model for Telegram voice notes). Every result has a **Links** panel: official site, fake look-alike, short link (expanded safely to where it goes), new or non-existent site; hidden links (`hxxp`, `[.]`, spoken "dot", Chinese 。) are un-hidden, and QR codes in screenshots are decoded. |
| **Finn, the fish** | A little scam-spotting friend who swims around the website. He flies in on your first visit, follows your pointer with his eyes, can be **picked up and moved anywhere** (mouse, finger or arrow keys; he remembers where you put him), tells a scam-safety tip when you tap him, and reacts to what you do: alarmed by a scam ("Don't tap that link!"), happy when you spot a trick in the games. He stirs the water background as he swims. He holds still for "reduce motion". Drawn in SVG, no images (`web/static/js/mascot.js`). |
| **Challenge family** | In Telegram (`/challenge`, or the button after a check), send a link; your parent plays a few rounds with no account and you see how they did. Shareable result card. The website has no button for it any more; friends cover that. |
| **Scam Road (3D)** | A little car with your character in the back window drives a three-lane road. A message is on the sign ahead; steer into the left lane for *scam*, the middle for *check first*, the right if it *looks fine*. Right lanes take you farther, three wrong turns end the drive, and every miss shows you the giveaway. Built with three.js (vendored, no CDN), with the message, buttons and results as real HTML over the canvas. The server deals the messages and **grades every lane**, so the answer is never in the page and a score cannot be forged; the same messages come from the seed bank, the authored bank and the scams your own family forwarded. Keyboard (arrows, 1/2/3), swipe, or big buttons; a slower "take it easy" mode; honours "reduce motion"; falls back to Inbox Rush where WebGL is missing. |
| **Daily Road, ghosts and the garage** | The **Daily Road** is the same messages in the same order for everyone who reads the same language that day (no private messages in it), so friends can race each other: **ghost cars** of your friends' best drives today (and your own) run beside the road at the pace they drove, spinning out where they crashed. A ghost is only the pace of each gate (right, careful or wrong), never an answer, so racing one cannot give anything away. Cars and hats for Finn are **earned, never bought** (a level, a distance, a streak, a Daily Road, passing a friend): plum, mint, sky, sunset, gold, midnight and a rainbow car; a cap, shades, a party hat, a scarf and a crown. Friends see your car on your ghost. Four **road themes** (auto day/night, night with stars and headlights, rain, festive with lanterns and confetti), **sound and music** made in the browser with the Web Audio API (no audio files; engine hum rising with speed, chimes, a crash, a soft arpeggio, each with an off switch and a mute key) and **vibration** on phones that support it. |
| **Live races** | Two to four people open a lobby (**Friends > Live race**, or a link), the host starts it and a shared countdown runs: everyone then drives the **same 12 gates at the same moment** and sees the others as live cars beside the road, moving at their *real* answer times. The most right answers wins; ties go to more hearts left, then to whoever finished first. Each drive is an ordinary server-graded one over a fixed length, so scores cannot be forged; the server settles the ranking, gives the XP (and the Duelist and Race champion badges), records who beat whom for a **head-to-head record**, and a rematch asks the same people back. A driver who stops answering is counted out after 45 s so nobody waits for a closed tab, there is no pause (the others do not wait), and the messages are read in the host's language. It uses a one-second poll rather than WebSockets, so it works behind any proxy. Friends who have notifications on are told when you open one. Races live in memory: a server restart ends the ones in progress. |
| **Seasonal themes** | The road dresses for the festival that is actually on (Singapore time): Chinese New Year, Hari Raya, Deepavali, Mid-Autumn, Christmas, National Day and Merdeka, each with its own sky, lamps or lanterns, fireworks, snow, a crescent moon or floating lanterns, a greeting in your language, and a line on the home page about festive-season scams. "Auto" picks the festival while it is on (then day or night by the clock); `?theme=deepavali` previews one and `BAITPROOF_TODAY=2026-11-08` pins the date. The dates are the governments' lists for 2026 and 2027 and **estimates after that** (`core/domain/seasons.py`): refresh them each year. |
| **Link Hunt** | A quick second game: four links each claim to belong to a real company (Maybank, Shopee, DBS, Pos Laju, PayPal ...) and one is a fake made with the tricks real scam sites use (an added word, a throwaway ending, look-alike letters, the real name buried in a longer address, a swapped letter, a hyphen through the name). Server-graded, three wrong taps end the round, every round trains the "fake website address" trick, with its own leaderboard. The fakes are the same ones the Check page flags: a test keeps the game and the checker in step. |
| **Family dashboard** | Inside a family group, `/family/dashboard` shows how the family is doing at spotting scams from **only what each person chose to share** (a tick box when you start or join, changeable any time): each person's practice score, streak and last practice, a **trick-by-person grid** (strong, getting there, weak, not tried; people who keep theirs private show as a dot), the family's soft spots (the tricks it is least ready for, from the people who share), a **Nudge** for someone who has gone quiet (a push notification, once a day; if they have none the page says so), and a short **weekly summary** to copy or send on WhatsApp. It never shows a message, a check or what anyone checked. |
| **Family groups** | Start a group for your family (up to 12, one group each), invite with a code or link, and share the scams you meet: only the **redacted** library text is shared (phone numbers, e-mails and link paths already removed), you choose each one and see exactly what goes, and it turns up as a **"From your family" gate** in everyone else's games (Scam Road, Inbox Rush, Your circle) so the family learns it before it reaches them. After a scam check there is a one-tap "Share with {family}", plus a family-only leaderboard. The owner can remove members; anyone can leave. |
| **Notifications** | Opt in on a device to be told **"Mei just passed your best"** (Web Push, in your language, at most three an hour). Needs the site's own VAPID keys (`python -m scripts.ops.make_vapid`, then `pip install -r requirements-extras.txt`) and HTTPS; without keys nothing about it appears. Subscriptions are only accepted for browsers' own push services (an allow-list), only for people with a profile, and the message carries a nickname and a distance, nothing else. |
| **Your character and your house** | Make a **character** (eight skin tones, eleven hairstyles including a tudung, a side part and spiky hair, seven outfits including a baju kurung, a polo and a kurta, a songkok, glasses, and a face: soft with rosy cheeks, plain, stubble, moustache, goatee or beard; colours): it is your picture on the leaderboards and the one who drives your car. Spend the **XP you earn** (the shop is priced so a house takes many rounds of play) on a 3D room built with three.js: 64 things (plants, furniture, decor, wall art, pets, and festival things sold only while their festival is on), five floors and six wall colours. Tap a thing to pick it, drag it to move it, turn it or put it away; your character walks around the furniture, and up to three **pets can follow you** around the room (tap a pet, then "Follow me"; visiting friends see them trot along too). The home page has a **progress card** (your character, level, streak and XP to spend). Friends can **visit your house** (read-only: they see the room, never your XP or what is in your cupboard). Spending never lowers your level, and the server checks every purchase and every layout. |
| **Profile, friends and leaderboard** | **Log in** from the header, or make a profile with a nickname and an avatar: **no email and no password**. You get a **sign-in key** (shown once, kept only as a hash) to use the same profile, records and practice on another device. Add friends with a six-character code or an **invite link** (share it on WhatsApp); friends see only your nickname, avatar and Scam Road distances, on a **this-week and all-time leaderboard**, and as **flags on the road** at each friend's best distance, with a live "Mei is 240 m ahead" strip. Either side can end a friendship; deleting your profile removes it all. There is no chat and no public board. |
| **Get help** | Every scam or victim result has an **official help panel**: the Singapore and Malaysia hotlines and reporting links (ScamShield 1799 and go.gov.sg/scamreport, the Anti-Scam Helpline 1800-722-6688, the National Scam Response Centre 997, Semak Mule), with tap-to-call on a phone. In Telegram it is a one-line pointer after a scam verdict, and `/report` shows the lot. `core/domain/helplines.py` holds the lines and the month they were last checked against government pages. |
| **Family alert and safe word** | `/family` in Telegram gives you a code for someone you trust; when you check something that looks like a scam they get a short note (the verdict and the tricks used, **never your message**), so they can call you. Opt-in, stoppable by either side (`/family off`, `/guard off`), capped at five helpers and six notes an hour. `/safeword` explains the family safe word. |
| **Install and share from WhatsApp** | The website is an **installable app** (use the browser's own Install or Add to Home Screen menu). On Android, once installed, **Baitproof appears in the Share sheet**: share a message or screenshot from WhatsApp, SMS or email and it is checked straight away (`web/routes/pwa.py`, a Web Share Target). The shared content is held in memory for five minutes, single use. iOS has no share targets, so there the Telegram bot or copy and paste is the way in. |
| **Colours** | A calm warm-neutral page with the brand purple, and an **accent colour for each part**: Check purple, Train teal, Friends rose, Records blue, the House amber (the games on the Train page each have their own too). The soft light behind the page and the water ripples mix different hues rather than shades of one, the logo and Finn stay purple, and every accent keeps white text at 4.5:1 or better in the light and dark looks (`tests/web/test_palette.py` checks it). The ripples react gently, and the page keeps them off on a device that is short on memory or asked to save data. |
| **Your language** | A language switcher (English / Bahasa Melayu / தமிழ் / 简体中文 / 繁體中文) on the website, `/lang` in Telegram. The explanation comes back in the language **you** read, whatever language the scam is in. Bahasa Melayu covers the whole interface, the verdicts, the trick explanations, the help lines and a Malay practice bank written around Malaysian and Singaporean scams (Pos Laju, TNB, PDRM, LHDN, Touch 'n Go, APK wedding cards ...). **Tamil (தமிழ்)** covers the whole interface, the Telegram bot, the verdicts, the trick explanations, the help lines and a 62-message Tamil practice bank (SingPost, DBS, CPF, IRAS, Shopee, a "new number" son, Deepavali draws ...); the next step on every Tamil result is always our own written line, and there is no Tamil rule pack (see [docs/TAMIL.md](docs/TAMIL.md)). |

## Why not a detector / ChatGPT / Hoxhunt?
- **Detectors** tell you once and forget you. Baitproof makes you harder to fool next time.
- **Enterprise trainers** (Hoxhunt, KnowBe4) are sold to IT departments and drill synthetic scams. Baitproof is for families and drills the **real scams reaching your circle**.
- **A plain LLM** is a good scam spotter and a poor judge of genuine messages: in our tests it called 12–33% of *genuine* messages scams (see Evaluation). Baitproof puts the model inside gates so it can raise suspicion but cannot invent evidence or clear a message it cannot read.

## Stack
- **Inference:** Nebius Token Factory (OpenAI-compatible, `https://api.tokenfactory.nebius.com/v1/`) with **NVIDIA Nemotron** `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, temperature 0, thinking mode off (`BAITPROOF_THINKING=1` to re-enable; it cost ~10x the tokens without improving verdicts). A whole Check costs well under a cent.
- **Web:** FastAPI + Jinja + vanilla JS, and three.js r160 for the 3D road (`web/static/vendor/`, unmodified, MIT, credited in NOTICE; vendored because the page's security policy only allows our own scripts). `pywebpush` (optional, `requirements-extras.txt`) sends the notifications. Strict CSP (no inline script or style), large type, high contrast, read-aloud. A frosted-glass look over a living background: a small WebGL shader draws water that ripples where you move, tap or click (`web/static/js/ripple.js`; off for "reduce motion", asleep when you stop, paused in background tabs, and a plain CSS glow takes over if the device can't keep up). Inter is served from `/static` (SIL OFL). **State:** SQLite. **Optional:** Tavily (review-style web checks), Telegram bot.
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
- **Evidence ledger.** Every finding is an `Evidence` record: kind (rule / intent / tool / reference / model), source, supports scam / safe / neutral, strength, and the quote it rests on. Model evidence counts half. The UI "How I decided" panel is this ledger.
- **Grounding and precondition gates.** A red flag whose quote is not in the message is dropped; a tactic needs its precondition to exist (no "fake link" without a link, no "asks for money" without an ask).
- **Arbiter.** Strong independent evidence means scam. Safe must be earned: no risky purpose, no unresolved links, a second look agreeing, and evidence that is not just the model. Model-only suspicion needs two consistent looks before it becomes "likely scam". Otherwise the honest answer is "not sure".
- **Confidence loop.** When the verdict depends on the model, a bounded loop (max 3 rounds, 10 model calls, 25 s) asks a planner which open question matters most, runs the allowed tools in parallel, and re-analyses, stopping as soon as the verdict is settled.
- **Tools** behind a gate (allow-list, arguments must come from the message, public hostnames only, budget, timeouts, never contacts the scammer's server): official-domain check against a brand table (now including the Malaysian parcel, electricity, tax and traffic-fine names) with look-alike detection and a weak "one letter away from {brand}" flag for typosquats such as `maybnak2u.com.my` (measured: no new flags on 251 distinct addresses in genuine real SMS, no change on the real-SMS evaluation), payment-rail check, phone check (offline rules for every country via `phonenumbers`: premium-rate, UK 070 "personal" and "one-ring" Caribbean numbers), a **public phishing blocklist** ([Phishing.Database](https://github.com/Phishing-Database/Phishing.Database), MIT, kept as a local file and refreshed daily, so no address is sent anywhere to be checked), domain age (RDAP, with the **certificate-transparency log** on crt.sh as a second clock when the registry cannot say), DNS sanity check, **company verification through Wikidata** (no key needed), **who registered a link's domain** (the registry's WHOIS record, compared with the company's own website: `mt.cn` is Meituan's because its contact address is `@meituan.com`), where a **short link** really goes, and Tavily brand lookup when a key is set.
- **Reference list** (`data/reference/entries.json`, `core/domain/reference.py`): a short, dated list of scam scripts that official bodies have named (Singapore Police and PDPC on officials who ask you to move money, Police and MAS on "safety accounts", MAS and ABS on bank links, India's I4C on "digital arrest", Malaysia's NSRC, Indonesia's OJK on unlicensed lenders). It is matched exactly (no embeddings, no model), only when the message also asks the reader to do something and never when the sentence is itself a warning. A match is independent evidence that names who said it and when ("Official warning" in "How I decided"), and it works in any language, including ones with no rule pack. Add a line when a new wave is announced; each entry carries the page it was checked against and the date.
- **Critic** looks again, with the verified facts, before anything is called safe.
- **Flywheel gate.** Only confident scams with independent evidence enter the training library, and only as tactics plus an abstracted, scrubbed example.

### Observability
Every check writes one JSON line to `logs/` (stages, tools, latency, tokens, cost; **no message text**, only a salted hash and length). `/admin` (set `BAITPROOF_ADMIN_TOKEN`) shows health, metrics, recent checks and user feedback ("was this right?"). A crash guard turns any internal error into a cautious "not sure". The Check page streams the stages live.

### Optional: few-shot retrieval
`core/ai/fewshot.py` can put the four most similar labelled examples from `data/fewshot/bank.json` into the prompt (`BAITPROOF_FEWSHOT=1`). Off by default; see Evaluation for what it did.

## Languages
| Message language | How it is checked |
|---|---|
| English | The full pipeline: rules, intent diagnosis, tools, evidence ledger, model, gates. |
| Chinese: Simplified, Traditional, or mixed with English | The same pipeline with a Chinese rule pack (`core/lang/zh.py`): deadlines and threats, claimed authorities, asks (pay, share a code, install, scan), 17 scam scripts (parcel fee, bank freeze, impersonated police, brush-order jobs, romance to investment, fake customer-service refund, boss and family emergencies, prizes, loans, social security, traffic fines, tickets, rentals ...), Chinese brands and official domains, links found inside unspaced Chinese text, and warnings such as "请勿泄露验证码" or public anti-fraud notices that must not be read as scams. Each rule is written once in Simplified and also matches Traditional. |
| Malay and Indonesian | The same, with a Malay/Indonesian pack (`core/lang/ms.py`): PDRM, LHDN, Kastam, SPRM, JPJ and bank impersonation, TAC/OTP read-outs, parcel and customs fees, "new number" family emergencies, task jobs and investment promises. |
| Tamil (தமிழ்) | The same, with a Tamil pack (`core/lang/ta.py`) written for Tamil script (Python's `\b` does not work beside Tamil vowel signs, so every pattern matches a stem and takes the rest of the word): "new number" family messages, fake police and "safe accounts", OTP and Singpass read-outs, bank, SingPost, CPF, IRAS and TNEB/Paytm/KYC phishing, like-and-earn and Telegram task jobs, VIP crypto groups, prize draws with a fee, and the warnings that must not be read as requests ("பகிர வேண்டாம்", "பகிராதீர்கள்": in Tamil the "don't" comes after the verb). It can say "looks fine" only for ordinary message types the rules recognise (a login code, a delivery, an appointment), never for a scam. |
| Anything else (Japanese, Korean, Hindi, Arabic, Spanish, French ...) | The model alone, inside the same gates. Because no independent rule can check these, Baitproof **never says "looks safe"** for them, only "not sure" (measured below: without this, 1 to 2 scams in 40 were called safe). |

**You choose the language of the answer**, not the message: a Chinese-speaking relative can check an English phishing email and read the explanation in Chinese, and the other way round. The website remembers it (cookie, else the browser's language), Telegram uses `/lang en|ms|zh|zh-Hant` (else Telegram's language). Verdict, giveaway, next step, every piece of evidence and the "How I decided" trace are translated; Traditional is derived from the Simplified text with OpenCC's character table (see [NOTICE](NOTICE)) plus a few Taiwan-style words, so wording is correct but not hand-polished. The practice, game and challenge messages for Chinese come from their own bank of 47 hand-written messages.

## Evaluation
`pytest` includes the rules-only check of the seed bank (free; a scam called safe fails it). `python -m scripts.eval.compare` runs the hard sets against a plain model call, `scripts.eval.real` the real datasets (see `data/external/README.md`) and `scripts.eval.multilingual` the translated ones; the data is downloaded by `scripts.data.fetch`, never committed. [scripts/README.md](scripts/README.md) lists every script and what it costs.

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

Earlier build, real English financial messages (Mendeley, 100 scams + 70 genuine): the plain model caught 98 / 100 but flagged **23 of 70 genuine notices (33%)** as scams; the pipeline caught 56 / 100, said "not sure" on 42, **called 2 safe** (the weakest result we have: they were a car-insurance claim approval and an annual-fee-waiver offer), and flagged 2 of 70 genuine ones. Not re-run on the final build.

**Honest reading:** a single model call is the better scam *catcher* and a poor judge of genuine messages; the pipeline gives up some catches (as "not sure", never as "safe") to stop calling a parent's real bank text a scam. That is the right trade for a family tool, but it means roughly one in four scams currently gets "not sure" rather than a firm verdict.

**3. Chinese.** Hand-written by us from common real scam scripts (39 scams, 40 genuine messages: Simplified, Traditional and mixed Chinese/English; `tests/data/zh/holdout.py`), written after the rules were designed and measured once before tuning. The first, untuned reading with rules only was 36 / 39 scams caught and **5 of 40 genuine messages falsely flagged** (a "don't share the code" warning read as a request, "5分钟内有效" read as a deadline, Alipay 支付宝 read as the verb "to pay", ...); after one round of fixes it is 0 of 40, which makes it a development set. Final build, live model:

| System | Scams caught | "Not sure" | Called safe | Genuine cleared | "Not sure" | False alarms |
|---|---|---|---|---|---|---|
| One plain model call | 37 / 39 | 2 | 0 | 26 / 40 | 1 | **13** |
| **Baitproof pipeline** | 36 / 39 | 3 | **0** | 32 / 40 | 8 | **0** |

The three scams it only calls "not sure" are short first-contact messages with no link, two of them with no request at all ("你好，请问是李先生吗？我是你同学的朋友…"): honestly ambiguous on their own. One honest negative result on the way: adding Chinese calibration examples and an always-on "reply language" line to the prompt made the model *more* suspicious (20 of 40 genuine cleared instead of 30), so both were removed (the language line is only added when the answer must be in a different language from the message).

**4. Malay and Indonesian** (`tests/data/ms/`, 20 + 20 written before the rules and 15 + 15 written after them). The first reading before any Malay rules was 1 of 20 scams caught. Both sets were then used to fix gaps (the 15 + 15 set first read 11 / 15 caught with 1 false alarm), so neither is a clean holdout. Final build, live model:

| Set | Plain model: caught / false alarms | Baitproof: caught / called safe / false alarms | Genuine cleared |
|---|---|---|---|
| 20 + 20 | 20 / 20, 6 of 20 flagged | 20 / 20, **0**, 0 flagged | 15 / 20 |
| 15 + 15 | 15 / 15, 4 of 15 flagged | 15 / 15, **0**, 1 flagged | 9 / 15 |

(The one false alarm, a genuine Indonesian "kode verifikasi" notice, was a rule bug that is now fixed and tested; it was not re-measured live.)

**5. Languages without rules** (Japanese, Korean, Hindi, Arabic, Spanish, French; Indonesian before its rules existed). The UCI SMS Spam Collection machine-translated into each language (`scripts.eval.multilingual`, 40 scams + 40 genuine per language). This checks that nothing breaks where the rules can't read the text; the translations are noisy (Hindi especially), so catch rates say little about real scams. A first run showed that a model-only "safe" let **1 to 2 scams in 40 through** in five of these languages, so for a language the rules can't read Baitproof now never says "safe":

| Language | Plain model caught | False alarms | Baitproof caught | "Not sure" | **Called safe** | False alarms |
|---|---|---|---|---|---|---|
| Indonesian | 40 / 40 | 4 / 40 | 24 / 40 | 16 | **0** | 0 |
| Japanese | 40 / 40 | 6 / 40 | 27 / 40 | 13 | **0** | 1 |
| Korean | 40 / 40 | 4 / 40 | 28 / 40 | 12 | **0** | 0 |
| Hindi | 32 / 40 | 2 / 40 | 3 / 40 | 37 | **0** | 0 |
| Arabic | 38 / 40 | 4 / 40 | 22 / 40 | 18 | **0** | 0 |
| Spanish | 38 / 40 | 4 / 40 | 23 / 40 | 17 | **0** | 0 |
| French | 40 / 40 | 6 / 40 | 23 / 40 | 17 | **0** | 0 |

**6. The languages we care most about, 24 Oct 2026** (`python -m scripts.eval.languages`; every set is written by us, not captured, and the Indonesian and Tamil text is not native-reviewed). Plain model = one model call; Baitproof = the whole pipeline. One live run each, and a run can move by one or two messages (a busy model makes more answers "not sure", never a scam).

| Set (scams + genuine) | Plain model: scams caught / genuine called a scam | Baitproof: scams caught / "not sure" / called safe | Genuine cleared / called a scam |
|---|---|---|---|
| English, real SMS, never tuned on (100 + 100) | 94 / 100, 12 of 100 | 79 / 20 / **1** (0 in the run before) | 43 of 100 / **0** |
| English, held out (44 + 22) | 44 / 44, 1 of 22 | 44 / 0 / **0** | 18 of 22 / **0** |
| English, Singapore and Malaysia, fresh (20 + 20) | 20 / 20, 2 of 20 | 19 / 1 / **0** | 14 of 20 / **0** |
| Chinese, held out (39 + 40) | 38 / 39, 13 of 40 | 36 / 3 / **0** | 33 of 40 / **0** |
| Chinese, fresh (20 + 20) | 20 / 20, 6 of 20 | 20 / 0 / **0** | 15 of 20 / **0** |
| Malay (20 + 20, and 15 + 15) | 20 / 20, 6 of 20 and 15 / 15, 4 of 15 | 20 / 0 / **0** and 15 / 0 / **0** | 16 of 20 and 10 of 15 / **0** |
| Indonesian, first reading of the holdout (25 + 25) | 25 / 25, 7 of 25 | 19 / 6 / **0** | 15 of 25 / **2** (opening hours read as a premium phone number) |
| Indonesian, fresh, read once after the fixes (20 + 20) | 20 / 20, 3 of 20 | 20 / 0 / **0** | 16 of 20 / **0** |
| Tamil, held out (25 + 25) | 25 / 25, 14 to 17 of 25 | 25 / 0 / **0** | 16 of 25 / **0** |
| Tamil, development (25 + 25) and practice bank (42 + 14) | 25 / 25, 8 of 25 and 42 / 42, 7 of 14 | 25 / 0 / **0** and 42 / 0 / **0** | 11 to 19 of 25 and 10 of 14 / **0** |

Before the Tamil rule pack existed, the same Tamil development set read 11 of 25 scams caught (the rest "not sure"), 0 of 25 genuine cleared and 2 false alarms; the practice bank read 25 of 42. The other first readings that exposed gaps (and what fixed them): the Indonesian holdout (opening hours "09.00-11.00" read as a premium phone number; short Indonesian messages detected as "other" so no rules ran on them; a courier update read as an impersonation; "do not share this code" read as a request; vocabulary such as KTP, pulsa, rb/jt, tilang, "lowongan driver"), a Chinese anti-fraud public notice called a scam (it quotes "safe account"), and an English `.apk` invitation. The Indonesian holdout and the Tamil practice bank are development sets now: they were read after the first run.

The same re-run on the machine-translated SMS of section 5 (30 + 30 per language, model only inside the gates) caught: Hindi 3, Spanish 14, Russian 15, Portuguese 15, Arabic 17, French 17, German 17, Japanese 18, Korean 21, Bengali 22, Turkish 22 and Indonesian 21 of 30, with two scams called safe (an English spam the translation left in English, in the Russian set, and a fast-food promotion in the Indonesian set) and one false alarm (Turkish). Those languages have no rules, so most of what they miss comes back as "not sure". A model that first translates the message to English was proposed and not tried.

**The reference list** (`data/reference/entries.json`) rarely changes a verdict on these sets (it spoke on 1 to 5 scams per set and on no genuine message): the rules already cover those scripts. Where it helps is any language with no pack, because a named script matches in any language: a Hindi "digital arrest" message read "not sure" without it and "likely scam" with it (one message, not a benchmark).

**Data caveats.** The English datasets are older (2003-2012 UK/Singapore/India SMS); "spam" is not always "scam"; some labelled-genuine finance messages were volunteer-written and look templated. Our own seed and hard sets are partly contaminated because rules were written after seeing failure categories, which is why the fresh train split is the headline number. None of the third-party data is committed.

## Telegram
```bash
pip install "python-telegram-bot>=21"
# .env: TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_USERNAME, BAITPROOF_URL
python -m bot.telegram_bot
```
Paste or forward a message to the bot for the same gated verdict. Commands: `/start`, `/quiz` (a five-question "scam or not?" round with buttons, graded by the same game engine as the website; `/quiz daily` is the Daily Challenge), `/challenge` (a forwardable "can you spot the scam?" link for a parent), `/link CODE`, `/unlink`, `/history`, `/score`, `/report` (official hotlines and where to report), `/family` and `/guard CODE` (family alerts, with consent), `/safeword`, `/lang en|ms|zh|zh-Hant`, `/help`. After a check that adds a trick to your practice the bot offers a quick quiz and a family challenge. Quiz messages defang scam links so quoting one never makes it tappable. Updates are handled concurrently (`BAITPROOF_BOT_CONCURRENCY`, default 16), so one slow screenshot read does not block other chats; each chat's profile stays isolated (tested).
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
pip install -r requirements-extras.txt  # optional: voice notes to text (faster-whisper) and QR codes in screenshots (OpenCV)
```
The share card renders Chinese when a CJK font is installed (`fonts-noto-cjk` on Linux, which `deploy/setup_vm.sh` installs) and falls back to the English card otherwise.
All settings are listed, with defaults, in [.env.example](.env.example).

## Safety & privacy
- **Screenshots** are the one thing we cannot scrub first: the picture goes unmodified to the vision model on Nebius, so names and numbers in it are seen by the model. EXIF and location data are stripped before sending, the picture is never stored, and the log gets only a small event (size, time, tokens), never the image or the text. `BAITPROOF_VISION=0` turns the feature off, and the website says this where you upload.
- **Voice**: Telegram voice notes are transcribed **on our own server** with a local model (faster-whisper) and never sent anywhere (the model downloads once from Hugging Face). On the website the browser's own speech service does the listening (in Chrome it is Google's), and Baitproof never receives the audio.
- **Short links**: only a known URL shortener is contacted, with one HEAD request that reads where it points, and never the destination itself, so we never touch a scammer's server. The shortener (and anyone who controls that link) can see one hit from our IP. `BAITPROOF_NET_TOOLS=0` turns it off.
- Cautious verdicts: "looks safe" always carries "…but verify via an official channel"; any red flag downgrades a safe verdict.
- "I already paid" messages get victim support, not analysis, and are never stored.
- We store **tactics and an abstracted example**, not messages. Emails, phone numbers (including mainland-China mobiles), resident ID numbers, card numbers and link paths are scrubbed deterministically before anything is stored or sent to a model; with the AI configured the example is also rewritten without names. In offline mode names in free text can survive scrubbing (limitation).
- **Records** keep the verdict and giveaway; the 120-character preview of the message is redacted, optional (`BAITPROOF_STORE_PREVIEW`, switchable per profile) and deletable per record or all at once.
- Logs contain no message text. No telemetry. Third-party datasets are never committed.
- **Where a message came from** is read from a screenshot (the app, the chat, the sender shown) or from a Telegram forward, shown back to you, and used as an unverified hint and to know which company to look up. It never decides a verdict by itself; the logs keep only its channel.
- The phishing blocklist is a file on the server (`data/cache/`, git-ignored): a link is looked up there, never sent to a service. Of the network tools, only the domain name is ever sent (to the public RDAP registry, the registry's WHOIS server, DNS, Wikidata, and the crt.sh certificate log), never the message, and the scammer's own server is never contacted. `BAITPROOF_NET_TOOLS=0` turns every network tool off; `BAITPROOF_BLOCKLIST=0` turns the list off.
- Encouraging tone: a miss is always "here's the tell you missed". Content is victim-facing only.

## Repository layout
```
core/domain/     tactics.py (12-tactic vocabulary), intents.py (19-purpose catalogue), schemas.py, privacy.py, helplines.py (official hotlines and reporting links), seasons.py (the festive calendar)
core/lang/       text.py (language detection, Simplified/Traditional-agnostic patterns), zh.py + ms.py + ta.py (Chinese, Malay/Indonesian and Tamil rule packs),
                 i18n.py + i18n_ui.py + i18n_bot.py + i18n_inputs.py (English text -> Simplified; Traditional is derived), i18n_ms.py + i18n_ta.py (the same text in Malay and in Tamil), data/ (OpenCC character tables)
core/storage/    db.py, library.py, model.py (personal model + score), history.py (records), links.py (Telegram link codes), family.py (family alert codes and helpers),
                 accounts.py (profiles, sign-in keys, friends), runs.py (leaderboards and ghost paths), groups.py (family groups and shared scams), dashboard.py (the family dashboard), push.py (Web Push)
core/ai/         llm.py (Nebius client), prompts.py, verify.py (Tavily), fewshot.py
core/inputs/     image.py (screenshots: vision model, QR), audio.py (voice notes: faster-whisper), errors.py
core/pipelines/  train.py, challenge.py, check/ (the gated pipeline: engine, gates, evidence, intent, scenarios, tools, blocklist, planner, preconditions, links, linkinfo, localize)
core/game/       pool.py, state.py (XP, levels, badges), engine.py (rounds, grading), road.py (Scam Road: server-graded endless drive and the Daily Road), garage.py (cars and hats earned by playing), linkhunt.py (Link Hunt), duel.py (live races), house.py (the shop and the rules of the room), looks.py (your character)
core/obs/        run, logger (JSONL), metrics, health
web/             main.py (app setup), pages.py (templates), ui.py (translation helpers), deps.py (profiles, rate limit, headers),
                 routes/ (check, inputs, records, practice, game, language, pwa, account, road, link, family, duel, house, push, admin), uploads.py (streaming image/audio upload), templates/, static/{css,js,img,vendor}
bot/             Telegram front-end (handlers.py is the tested logic)
data/            seeds/ (curated scams + genuine messages, en, zh and ms), fewshot/ (reference bank), external/ (downloaded, ignored)
scripts/         eval/ (compare, real, multilingual), data/ (fetch, seed_demo), ops/ (verify_setup, refresh_blocklist, make_vapid), common.py
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
- The Malay and Tamil interfaces, help text and practice banks were written by us (the Tamil by AI translators following one glossary) and have **not been reviewed by a native speaker** yet; expect some stiff phrasing. Tamil and Indonesian have rule packs of their own now (see the Evaluation), but both were written by us and measured only on sets we wrote ourselves, so treat the numbers as a development signal. Indonesian messages are checked by the Malay pack and answered in Malay or English; Tamil written in Latin letters ("Tanglish") is not recognised as Tamil. Traditional Chinese text is auto-converted from Simplified, so some wording is mainland-style.
- The official hotline numbers were checked against government pages in October 2026; numbers change, so recheck `core/domain/helplines.py` (and update `VERIFIED`) before relying on it.
- Accounts store a nickname, a character (a short look code), a hash of the sign-in key, friendships and Scam Road scores, in the shared database; never a message, an email or a password. A profile id is the session cookie, so it never appears in a page or an API answer (other people get a separate public id). Friends only make sense in public mode (`BAITPROOF_MULTIUSER=1`); a single-user copy has one profile. A friend is added by a code or link its owner chose to share, so treat the invite link like a house key.
- Scam Road needs WebGL (software rendering works, slowly). Sound only starts after you press Start (browsers insist), and phone vibration is Android only.
- Seasonal dates after 2027 are estimates, and the lunar and Hindu festivals can move by a day: the windows are generous, but update the table each year.
- Notifications need HTTPS (or localhost), the site's VAPID keys and a browser with Web Push; on iPhone they work only once the site is installed to the Home Screen. A friend's ghost shows how they drove, not what they answered, but it is a replay of pace, not a recording of their screen: crash timing is approximate.
- Family groups share only the redacted example, but a redacted scam can still be recognisable to the family it came from; that is the point, and each share is a choice. Distances are computed on the server from graded answers, but a friend group is a trust circle, not a tournament: someone who memorises the ~50 seed messages can score high.
- Family alerts fire for checks made in Telegram only (the website has no chat to send to). The share-from-WhatsApp route works on Android; iOS has no share targets.
- Future: resuming a race after a page reload, spectators, a WhatsApp bot, a native-speaker review of the Malay, Indonesian and Tamil text, more rule packs (Japanese, Korean, Hindi), checking the reference list against the official pages before each release.

## License
MIT
