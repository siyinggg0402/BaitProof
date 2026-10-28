# Evaluation and limitations

The full measurements behind the summary table in the [README](../README.md#results), kept as they were first written: what was measured, the first reading before any tuning, and the negative results.

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

**7. Other models, 27 Oct 2026** (the same one-call baseline as everywhere above: the system prompt in `scripts/common.py`, temperature 0, one live run per model, all on Nebius Token Factory). 389 labelled messages: English hard set 3 (20 + 20), English Singapore (20 + 20), real SMS never tuned on (50 + 50 of the 100 + 100 sample), Chinese held out (39 + 40), Malay (20 + 20), Indonesian fresh (20 + 20), Tamil held out (25 + 25): 194 scams and 195 genuine messages. Pooled across the five languages:

| Model | Scams caught (of 194) | Scams called safe | Genuine wrongly flagged (of 195) | Seconds per call |
|---|---|---|---|---|
| DeepSeek-V4.1-Flash | 189 | 2 | **1** (0.5%) | 5.7 |
| gpt-oss-120b | 190 | 3 | 5 (3%) | 4.2 |
| Qwen3-235B-A22B | 189 | 0 | 6 (3%) | 3.3 |
| Nemotron 3 Super 120B-A12B | 189 | 0 | 7 (4%) | 3.6 |
| Qwen3-30B-A3B | 188 | 1 | 31 (16%) | 3.5 |
| **Nemotron 3 Nano 30B-A3B (ours)** | 191 | 0 | **51** (26%) | 3.8 |
| Gemma-3-27B | 193 | 0 | 62 (32%) | 4.3 |

Catching scams is easy for all of them. The difference is judging genuine messages: Nemotron Nano flags about a quarter on its own, like Gemma, and unlike the larger models; within the Nemotron family the bigger Super is far better calibrated at the same speed. Third-party price lists (not confirmed against Nebius's own) put Super at about four times Nano's price, which is why the app runs Nano.

**The same messages through the whole pipeline** (the gates; network tools off for this run; the pipeline's prompts were written for Nemotron Nano). Five of the sets above, 154 scams and 155 genuine messages (the Indonesian set and the English Singapore set were left out), for the two models whose runs finished:

| Model | Plain call: caught / called safe / genuine wrongly flagged | Whole pipeline: caught / "not sure" / called safe / genuine wrongly flagged |
|---|---|---|
| Nemotron 3 Nano 30B-A3B | 151 / 0 / 44 of 155 | 133 / 21 / **0** / **0** of 155 |
| Qwen3-30B-A3B | 148 / 1 / 28 of 155 | 139 / 15 / **0** / **1** of 155 |

So the gates remove the over-flagging whichever model sits inside them, at the price of 10 to 14% of scams becoming "not sure". The pipeline runs for DeepSeek-V4.1-Flash, Gemma-3-27B and Nemotron 3 Super were started but not finished, so there is no pipeline comparison for them. Caveats: our own sets (the Chinese, Malay, Indonesian and Tamil ones are written by us), one run each, so read any figure as plus or minus a few messages. To repeat a plain-call run for one model: `NEBIUS_MODEL=<model id> python -m scripts.eval.languages --modes llm --sets en-hard3,en-sg,en-real,zh-holdout,ms-holdout,id-fresh,ta-holdout` (that script uses all 100 + 100 of the real-SMS sample, not 50 + 50).

## Limitations
- The deploy files run the live demo, but the one server is a single point of failure: there is no second copy, only a nightly backup on the same disk (copy it off now and then, see deploy/README.md). The demo's data resets if the server is rebuilt.
- The Telegram connector is tested through its handlers; its connection to the live Telegram API is checked by hand, not by the test suite.
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
