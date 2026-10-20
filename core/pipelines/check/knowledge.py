"""Static detection knowledge (patterns, brand list). Pure data, no logic."""
from __future__ import annotations

import re

C = lambda p: re.compile(p, re.I | re.S)  # noqa: E731

VICTIM_RE = C(
    r"\bi (?:already |have |just )?(?:paid|sent (?:them|the|it|money)|transferred|gave (?:them|him|her)|clicked|installed|shared (?:the|my))\b"
    r"|\bi(?:'ve| have) been scammed\b|\bi think i (?:was|got) scammed\b")

# A message that tries to instruct the checker is itself a red flag.
INJECTION_RE = C(r"ignore (?:all |the |any )?(?:previous|above|prior) (?:instructions?|rules?)|system prompt|you are now\b|mark (?:this|it) as (?:safe|legit)|respond (?:only )?with.{0,20}\bsafe\b|\bas an ai\b|verdict\s*:")

PRESSURE_RE = C(r"\bwithin \d+ ?(?:hours?|hrs?|minutes?|mins?)|\bimmediately\b|\bright now\b|\burgent(?:ly)?\b|\btoday (?:at|by)\b|\bby tonight\b|\blast (?:chance|warning)\b|\bact now\b|\bfinal (?:notice|demand|warning)\b|\b(?:offer|deal) ends\b|\babout to expire\b|\bbefore midnight\b|\bat once\b|\blimited spots?\b|\b(?:closes?|ends?|expires?|expiring|deadline)\b[^.!?]{0,20}\b(?:tonight|today|midnight)\b|\bor (?:your|the) .{0,30}(?:will be|is) (?:cut|closed|suspended|blocked|returned|arrested|frozen)")

PREMIUM_RE = C(r"\b\d+(?:\.\d+)?\s?p\s?(?:per|/)\s?(?:min|msg|message|text|week|wk)\b|\bppm\b|\b[£$€]\s?\d+(?:\.\d{2})?\s?(?:/|per)\s?(?:msg|min|text|wk|week|month)\b"
               r"|\bcosts?\s+[£$€]\s?\d+(?:\.\d+)?|\bcosts?\s+\d+(?:\.\d+)?\s?(?:p|ppm|pence)\b|\b(?:txt|text|sms|send|reply)\b[^.!?\n]{0,70}\b(?:to|2)\s*\d{4,6}\b|\b\d{3,}p\b[^.!?\n]{0,20}\b(?:msg|message|text)")

RAILS = {  # irreversible payment rails
    "gift-card": C(r"\bgift ?cards?\b|\b(?:google play|itunes|steam|apple|amazon|prepaid) cards?\b"),
    "crypto": C(r"\bbitcoin\b|\bcrypto(?:currency)?\b|\busdt\b|\busdc\b|\bbtc\b|\beth(?:ereum)?\b|\bsolana\b|\bdogecoin\b"),
    "wire": C(r"\bwire (?:transfer|the money)\b|\bwestern union\b|\bmoneygram\b"),
    "safe-account": C(r"\bsafe account\b"),
}

RULES: dict[str, list[re.Pattern]] = {k: [C(p) for p in v] for k, v in {
    "urgency-pressure": [PRESSURE_RE.pattern],
    "authority-spoofing": [r"\b(?:this is|i am|i'm|from the|my name is)\b[^.!?]{0,30}\bofficer\b|\bofficer (?-i:[A-Z][a-z]+)\b|\bpolice officers?\b|\bofficers (?:will|are|have|were)\b", r"\bfraud department\b", r"\bdo not speak to\b", r"\bcyber ?crime\b", r"\bsecurity team\b", r"\bdo not tell (?:your|anyone)", r"\bwarrant\b", r"\bfraud (?:case|department)\b"],
    "otp-credential-phish": [r"\b(?:6|4|six|four)[- ]digit code\b", r"\bverification code\b.*\b(?:reply|send|read)\b", r"\bconfirm your password\b", r"\bone[- ]time (?:code|password)\b"],
    "too-good-to-be-true": [r"\b\d[\d.,]* ?million\b", r"\bcongratulations\b[^.!?]{0,60}\b(?:won|winner|selected|prize|reward|gift|free|claim|lucky)\b", r"\byou(?:'ve| have) (?:been selected|won)\b", r"\bguaranteed returns?\b", r"\bno risk\b", r"\bno experience\b", r"\bearn \$?\d+ (?:a|per) day\b"],
    "emotional-manipulation": [r"\b(?:accidentally|mistakenly|by mistake)\b.{0,30}\b(?:sent|transferred|paid|deposited)\b", r"\b(?:new (?:phone|number)|lost my phone|phone (?:broke|died|fell))\b", r"\bemergency\b", r"\b(?:mum|mom|grandma|grandpa|dad)\b.*\b(?:trouble|stuck|lost|broke|stolen|hospital|jail)\b", r"\bdon'?t (?:tell|call)\b", r"\bplease don'?t call\b", r"\bi love you\b.*\$", r"\bcustoms\b"],
    "remote-access-request": [r"\banydesk\b|\bteamviewer\b|\bquicksupport\b|\bultraviewer\b", r"\binstall (?:the |an? )?(?:app|software|program)\b", r"\bremote (?:access|support|session)\b", r"\b(?:connect to|control|take over|access) your (?:screen|computer|pc|laptop|device)\b"],
    "advance-fee": [r"\b(?:processing|release|legal|insurance) (?:fee|deposit)\b", r"\bpay (?:a |the )?(?:small )?(?:fee|tax)\b.*\b(?:release|receive|claim|prize)\b", r"\bno credit check\b", r"\badmin(?:istration)? fee\b|\bfree (?:government )?(?:solar )?grant\b", r"\bunclaimed\b|\bnext of kin\b|\bbe my partner\b|\bno heirs?\b|\bgovernment grant\b", r"\bshipping\b.*\$|\$.*\bshipping\b"],
    "impersonation-official": [r"\birs\b|\bmedicare\b|\bsocial security\b|\bhmrc\b|\btax (?:office|refund)\b", r"\b(?:parcel|package) (?:is )?on hold\b|\bparcel is held\b", r"\bdhl\b|\bfedex\b|\busps\b|\bups\b"],
    "investment-crypto": [r"\b\d+x (?:in|returns?|gains?|your)\b", r"\bpresale\b|\bairdrop\b|\bearly backers?\b", r"\btrading signals?\b", r"\b\d{3,}% (?:monthly |weekly )?returns?\b", r"\bprofit\b.*\bwithdraw\b", r"\bforex\b"],
    "job-task-scam": [r"\$\d+ (?:a|per) day\b", r"\bsimple (?:social media |online )?tasks\b", r"\bper task\b|\bcomplete \d+ tasks\b", r"\bboost (?:app )?ratings?\b", r"\btop up your (?:balance|account)\b", r"\bdeposit\b.*\b(?:activate|unlock)\b", r"\blike videos\b"],
}.items()}

BRANDS = {  # brand -> its real domain. Used to spot imitation (hard evidence) and to recognise genuine links (reassuring evidence).
    "dhl": "dhl.com", "paypal": "paypal.com", "amazon": "amazon.com", "netflix": "netflix.com", "apple": "apple.com", "microsoft": "microsoft.com",
    "fedex": "fedex.com", "usps": "usps.com", "medicare": "medicare.gov", "irs": "irs.gov", "chase": "chase.com", "wellsfargo": "wellsfargo.com",
    "hsbc": "hsbc.com", "google": "google.com", "spotify": "spotify.com", "github": "github.com", "zoom": "zoom.us", "uber": "uber.com",
    "whatsapp": "whatsapp.com", "facebook": "facebook.com", "instagram": "instagram.com", "linkedin": "linkedin.com", "dropbox": "dropbox.com",
    "adobe": "adobe.com", "ebay": "ebay.com", "walmart": "walmart.com", "costco": "costco.com", "bestbuy": "bestbuy.com", "airbnb": "airbnb.com",
    "booking": "booking.com", "expedia": "expedia.com", "royalmail": "royalmail.com", "evri": "evri.com", "dpd": "dpd.co.uk", "ups": "ups.com",
    "auspost": "auspost.com.au", "bankofamerica": "bankofamerica.com", "citibank": "citi.com", "barclays": "barclays.co.uk", "lloyds": "lloydsbank.com",
    "natwest": "natwest.com", "santander": "santander.co.uk", "americanexpress": "americanexpress.com", "venmo": "venmo.com", "coinbase": "coinbase.com",
    "binance": "binance.com", "steam": "steampowered.com", "telegram": "telegram.org", "tiktok": "tiktok.com", "snapchat": "snapchat.com",
    "twitter": "twitter.com", "youtube": "youtube.com", "yahoo": "yahoo.com", "outlook": "outlook.com", "icloud": "icloud.com", "docusign": "docusign.com",
    "shopify": "shopify.com", "etsy": "etsy.com", "aliexpress": "aliexpress.com", "tesco": "tesco.com", "argos": "argos.co.uk", "vodafone": "vodafone.com",
    "qantas": "qantas.com", "britishairways": "britishairways.com", "doordash": "doordash.com", "ubereats": "ubereats.com", "nhs": "nhs.uk",
    "hmrc": "gov.uk", "ato": "ato.gov.au", "mygov": "mygov.au", "norton": "norton.com", "mcafee": "mcafee.com", "cashapp": "cash.app", "zelle": "zellepay.com",
}
# Brand words that are also ordinary words or short names: only an exact host token counts, and mentions in the text don't count.
AMBIGUOUS_BRANDS = {"apple", "uber", "steam", "booking", "ups", "ato", "zoom", "chase", "outlook", "twitter", "target", "square", "shell", "dpd", "nhs", "irs"}
BAD_TLDS = (".xyz", ".top", ".click", ".icu", ".info", ".online", ".site", ".shop", ".live")
SHORTENERS = {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "is.gd", "cutt.ly", "rb.gy"}
LEET = str.maketrans({"0": "o", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
