# Tamil (தமிழ்) in Baitproof

Tamil is one of Singapore's four official languages, so the website, the Telegram bot and the games speak it. This page says what is covered, what is not, and what a Tamil speaker should check first.

## What is covered
- **The whole interface** (about 1,300 strings): the website, the games, the house, the Telegram bot, the help panel with the Singapore and Malaysia hotlines. The table is `core/lang/i18n_ta.py`; the English text is the key, as for the other languages, and anything missing falls back to English.
- **The twelve scam tricks** (name, summary, the giveaway, what to do) in `TACTICS_TA`.
- **A Tamil practice bank** (`data/seeds/ta.json`, 62 messages: 42 scams and 20 that are not, 6 of them "check first"), written around Singapore and Malaysia: SingPost, DBS/POSB, OCBC, UOB, CPF, IRAS, Shopee, a "new number" son or daughter, fake Deepavali draws and Pongal gold offers, and genuine messages to compare with.
- **Voice**: speaking in Tamil on the English page (`ta-IN`), reading answers aloud in a Tamil voice, voice notes with a Tamil hint.
- **Share card**: drawn in Tamil when the server's Pillow has text shaping and a Tamil font (`fonts-noto-core`); otherwise the card is in English (never broken letters).

## What is not
- **A Tamil rule pack (`core/lang/ta.py`).** A Tamil message is checked by phrase rules as well as the model and the checks that need no language (look-alike links, phone numbers, the public phishing list). The rules catch the common scripts (a "new number" child, fake police and a "safe account", OTP read-outs, bank and parcel phishing, like-and-earn jobs, VIP crypto groups, prize draws with a fee) and recognise ordinary messages (a login code, a delivery, an appointment) well enough to clear them. It is **never "safe"** for anything that looks like a scam. Tamil written in Latin letters ("Tanglish") is not recognised as Tamil. The patterns were written by us and tested only on messages we wrote (`tests/data/ta/`), so a Tamil reader's corrections are the most useful thing you can send.
- **The next step on a Tamil result is always our own written line** for the trick, not the model's Tamil, because nobody has read the model's Tamil for mistakes.
- **No native-speaker review yet.** The text was written by AI translators who followed one glossary. Expect some stiff phrasing.

## For a Tamil reviewer: look at these first
1. Words that mix a Latin brand with a Tamil case ending, written with a hyphen (`Telegram-ஐ`, `OTP-ஐ`, `DBS-இன்`). Is that how you want it?
2. Loanwords chosen for everyday use: டெபாசிட் (deposit), கிரிப்டோ (crypto), கராஜ் (garage), தீம் (theme), போட் (bot), ஃபார்வர்ட் / முன்னனுப்பு (forward).
3. "Lantern" and "lamp" share one word (விளக்கு) in the house shop (red lanterns, moon lanterns, lantern stand).
4. Game words: வாயில் (gate on Scam Road), போட்டியிடு (race, chosen over பந்தயம், which can mean a bet), தலைவன் (boss), தொடர் சரியான பதில்கள் (combo; long for a label).
5. Fragments built around placeholders: "{brand}-இன்", "{name} வீடு", "{festival} காலத்தில் மட்டும்", "Gate {n} of {m}" (`{m} வாயில்களில் {n}-வது`), and sentence tails after a link ("... சேர்க்க", "... பார்க்க").
6. Malay and Malaysian names written in Tamil script: பாஜு குருங், ஜாலுர் கெமிலாங், கெத்துப்பாட், சொங்கோக், வாவ் பட்டம், பெலிட்டா.
7. The Hari Raya greeting "Maaf zahir dan batin" is an approximate Tamil rendering, not literal.
8. The practice bank: religious and cultural wording (temple annadhanam, Pongal, Deepavali, Thaipusam) should be respectful, and the tell in t02 explains "the real site is the last part of the address" more technically than the other languages do.

## How to correct it
Edit `core/lang/i18n_ta.py` (one line per string: `"English text": "தமிழ்"`; keep every `{placeholder}`), or `data/seeds/ta.json`. `pytest tests/core/lang/test_ta.py tests/web/test_lang_ta.py` checks that every key is still covered, the blanks match, no Chinese or English is left behind, and that no Tamil practice message is ever called "safe".
