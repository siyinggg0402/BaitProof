"""Static detection knowledge (patterns, brand list). Pure data, no logic."""
from __future__ import annotations

import re

C = lambda p: re.compile(p, re.I | re.S)  # noqa: E731

VICTIM_RE = C(
    r"\bi (?:already |have |just )?(?:paid|sent (?:them|the|it|money)|transferred|gave (?:them|him|her)|clicked|installed|shared (?:the|my))\b"
    r"|\bi(?:'ve| have) been scammed\b|\bi think i (?:was|got) scammed\b")

# A message that tries to instruct the checker is itself a red flag.
INJECTION_RE = C(r"ignore (?:all |the |any )?(?:previous|above|prior) (?:instructions?|rules?)|system prompt|you are now\b|mark (?:this|it) as (?:safe|legit)|respond (?:only )?with.{0,20}\bsafe\b|\bas an ai\b|verdict\s*:")

PRESSURE_RE = C(r"\bwithin \d+ ?(?:hours?|hrs?|minutes?|mins?)|\bimmediately\b|\bright now\b|\burgent(?:ly)?\b|\btoday (?:at|by)\b|\bby tonight\b|\blast (?:chance|warning)\b|\bact now\b|\bfinal (?:notice|demand|warning)\b|\b(?:offer|deal) ends\b|\babout to expire\b|\bbefore midnight\b|\bat once\b|\blimited spots?\b|\bor (?:your|the) .{0,30}(?:will be|is) (?:cut|closed|suspended|blocked|returned|arrested|frozen)")

RAILS = {  # irreversible payment rails
    "gift-card": C(r"\bgift ?cards?\b|\b(?:google play|itunes|steam|apple|amazon|prepaid) cards?\b"),
    "crypto": C(r"\bbitcoin\b|\bcrypto(?:currency)?\b|\busdt\b|\bbtc\b"),
    "wire": C(r"\bwire (?:transfer|the money)\b|\bwestern union\b|\bmoneygram\b"),
    "safe-account": C(r"\bsafe account\b"),
}

RULES: dict[str, list[re.Pattern]] = {k: [C(p) for p in v] for k, v in {
    "urgency-pressure": [PRESSURE_RE.pattern],
    "authority-spoofing": [r"\bofficers?\b", r"\bfraud department\b", r"\bdo not speak to\b", r"\bcyber ?crime\b", r"\bsecurity team\b", r"\bdo not tell (?:your|anyone)", r"\bwarrant\b", r"\bfraud (?:case|department)\b"],
    "otp-credential-phish": [r"\b(?:6|4|six|four)[- ]digit code\b", r"\bverification code\b.*\b(?:reply|send|read)\b", r"\bconfirm your password\b", r"\bone[- ]time (?:code|password)\b"],
    "too-good-to-be-true": [r"\b\d[\d.,]* ?million\b", r"\bcongratulations\b", r"\byou(?:'ve| have) (?:been selected|won)\b", r"\bguaranteed returns?\b", r"\bno risk\b", r"\bno experience\b", r"\bearn \$?\d+ (?:a|per) day\b"],
    "emotional-manipulation": [r"\b(?:mum|mom|grandma|grandpa|dad)\b.*\b(?:trouble|stuck|lost|broke|stolen|hospital|jail)\b", r"\bdon'?t (?:tell|call)\b", r"\bplease don'?t call\b", r"\bi love you\b.*\$", r"\bcustoms\b"],
    "remote-access-request": [r"\banydesk\b|\bteamviewer\b|\bquicksupport\b|\bultraviewer\b", r"\binstall (?:the |an? )?(?:app|software|program)\b", r"\bremote (?:access|support|session)\b"],
    "advance-fee": [r"\b(?:processing|release|legal|insurance) (?:fee|deposit)\b", r"\bpay (?:a |the )?(?:small )?(?:fee|tax)\b.*\b(?:release|receive|claim|prize)\b", r"\bno credit check\b", r"\bunclaimed\b|\bnext of kin\b|\bbe my partner\b|\bno heirs?\b|\bgovernment grant\b", r"\bshipping\b.*\$|\$.*\bshipping\b"],
    "impersonation-official": [r"\birs\b|\bmedicare\b|\bsocial security\b|\bhmrc\b|\btax (?:office|refund)\b", r"\b(?:parcel|package) (?:is )?on hold\b|\bparcel is held\b", r"\bdhl\b|\bfedex\b|\busps\b|\bups\b"],
    "investment-crypto": [r"\btrading signals?\b", r"\b\d{3,}% (?:monthly |weekly )?returns?\b", r"\bprofit\b.*\bwithdraw\b", r"\bforex\b"],
    "job-task-scam": [r"\bper task\b|\bcomplete \d+ tasks\b", r"\bboost (?:app )?ratings?\b", r"\btop up your (?:balance|account)\b", r"\bdeposit\b.*\b(?:activate|unlock)\b", r"\blike videos\b"],
}.items()}

BRANDS = {"dhl": "dhl.com", "paypal": "paypal.com", "amazon": "amazon.com", "netflix": "netflix.com",
          "apple": "apple.com", "microsoft": "microsoft.com", "fedex": "fedex.com", "usps": "usps.com", "medicare": "medicare.gov",
          "irs": "irs.gov", "chase": "chase.com", "wellsfargo": "wellsfargo.com", "hsbc": "hsbc.com", "google": "google.com"}
BAD_TLDS = (".xyz", ".top", ".click", ".icu", ".info", ".online", ".site", ".shop", ".live")
SHORTENERS = {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "is.gd", "cutt.ly", "rb.gy"}
LEET = str.maketrans({"0": "o", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
