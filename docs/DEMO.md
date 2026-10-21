# Demo video (under 3 minutes)

The hackathon asks for a video under 3 minutes. This is a shot list with the words to say (about 400 words at a calm pace) and copy-ready messages. Record at 1080p, browser at 1280x800, text size normal.

## Before you press record
1. Local app, real model: `uvicorn web.main:app` with `NEBIUS_API_KEY` set. Open it once and check one message so the model is warm (a cold start can take up to a minute). Public demo URL instead? Use it, but warm it up the same way.
2. A believable account: `python -m scripts.data.seed_demo` (honestly seeded: some tricks strong, one weak). Do NOT run it on the public server.
3. Tabs open in this order: Check, Train, Records. A second window with Telegram (the bot linked to this profile: Records > *Connect Telegram*). Language set to English.
4. Hide the bookmarks bar, the terminal and anything containing a key. Never show `.env`.
5. Copy these into a note you can paste from:

| Use | Message |
|---|---|
| English scam | `DHL: Your parcel is on hold. Pay the $1.99 fee within 24 hours or it will be returned. Pay now: dhl-fee-pay.xyz/track` |
| Family scam | `Hi grandma, it's me. I'm in trouble and need cash. Please buy four $100 gift cards and send me the numbers. Don't tell Mom.` |
| Genuine | `Hi, this is Dr. Lee's clinic. Reminder: your appointment is tomorrow at 10:30am. Please call the number on your appointment card to reschedule.` |
| Chinese scam | `【顺丰速运】您的快递因地址不详无法派送，请于24小时内点击 http://sf-express-cn.top/addr 补全信息，逾期将退回。` |
| Chinese police scam | `我是市公安局的李警官，您的身份证被人冒用，涉及一起诈骗案，需要您配合调查，把名下资金转入我们提供的安全账户进行核查，请不要告诉任何人。` |
| Malay scam | `Maybank2u: Akaun anda telah disekat kerana aktiviti mencurigakan. Sahkan butiran anda di http://maybank-secure-login.cc sekarang.` |

## Script

| Time | On screen | Say |
|---|---|---|
| 0:00 | The English scam on a phone screenshot or pasted into the box, cursor on it | "Your parents get messages like this every week. Detectors tell you once and forget you. Baitproof is different: it makes your family harder to fool next time." |
| 0:15 | Paste it, press Check. The live gates tick by | "I paste the message. Watch the gates: it reads the message, works out what it asks of me, checks the link and the sender, then the model reviews it, then rules weigh the evidence. Nemotron on Nebius Token Factory does the reading; deterministic gates make the decision." |
| 0:35 | The verdict, the giveaway, "What to do", then open the evidence list | "A scam, and it points at the one giveaway: a fee plus a deadline, and a fake DHL address. Every red flag is evidence with a quote from the message. The model proposes, the gates decide: it can't invent a red flag that isn't in the text, and it can't talk us out of a hard one." |
| 0:55 | Paste the genuine clinic message | "And a normal message is not called a scam. A plain model call flags a quarter of genuine messages; that destroys trust, so we measured it and built against it." |
| 1:10 | Switch the language to 简体中文; paste the Chinese scam; show the Chinese result | "Our families aren't only in English. Same pipeline, with its own Chinese rules: it finds the link inside unspaced text, knows the bank and courier brands, and answers in the language you read. Simplified, Traditional, even an English scam explained in Chinese. Malay and Indonesian have rules too." Switch back to English. |
| 1:35 | Telegram: forward the Family scam to the bot, show the reply | "Real life happens in chat, so the bot gives the same verdict in Telegram." |
| 1:45 | Telegram: `/quiz`, tap two answers, show the feedback | "And young people don't open a website to practise, so the practice comes to them: a five-question quiz right in the chat." |
| 2:00 | Website: Records (the Telegram check is there), then Train | "Everything I check, in Telegram or on the web, lands in one record, and the tricks go straight into my practice. It learns which tricks fool *me* and drills those." |
| 2:15 | Train: a drill; or the Game: Spot the Tell or a boss fight | "Practice, a game, a boss fight per trick. Answers are graded on the server." |
| 2:30 | `/challenge` in Telegram, open the link on the phone, play one round, show the result card | "The loop closes with the family: I send my mother a two-minute challenge, no account, and she gets a score card." |
| 2:42 | The README evaluation table, or the `/admin` health page | "We measured it honestly: on real SMS we never tuned on, zero scams called safe, and about 2 percent false alarms where a plain model gives 12 to 33. Where our rules can't read a language, we never say 'looks safe'. Logs hold no message text." |
| 2:55 | Logo, repo URL | "Baitproof. Open source, MIT. Thank you." |

## If something goes wrong
- A slow first check: say nothing, cut it in editing, or warm up first. The app warms the model at start.
- No Telegram: cut 1:35-1:45 and 2:30; the website covers the story.
- Keep the final claim to what the README says. The numbers are in [README.md](../README.md#evaluation); do not round them in your favour.
