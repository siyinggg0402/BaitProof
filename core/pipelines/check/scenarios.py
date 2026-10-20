"""Known scam scripts. A message matches a script only when several independent signs line up (min), so a harmless
'your parcel was delivered' (one sign) never matches while a parcel-fee scam (parcel + fee + link + 'on hold') does."""
from __future__ import annotations

import re
from dataclasses import dataclass

from core.lang import ms as MS
from core.lang import zh as ZH
from core.lang.text import Dual

I = re.I


@dataclass(frozen=True)
class Scenario:
    id: str
    label: str
    signals: tuple  # Dual patterns (English + Chinese twin): each one that matches is one sign
    min: int = 3
    must: tuple = ()  # indexes of signs that MUST be present (the sign that separates a scam from a normal notice)


def _s(id: str, label: str, signals: list[str], min: int = 3, must: tuple = ()) -> Scenario:
    zh, ms = ZH.SCENARIO_SIGNS.get(id), MS.SCENARIO_SIGNS.get(id)
    assert zh is None or len(zh) == len(signals), id  # the Chinese and Malay signs line up one-to-one with the English ones (so `must` means the same)
    assert ms is None or len(ms) == len(signals), id
    return Scenario(id, label, tuple(Dual(p, zh[i] if zh else None, ms[i] if ms else None) for i, p in enumerate(signals)), min, must)


# Sentences that deny the risky thing ("we will never ask for your PIN") must not count as signs of it.
NEGATED = Dual(r"[^.!?\n]*\b(?:never|do not share|don'?t share|not share|will not ask|won'?t ask)\b[^.!?\n]*[.!?]?", ZH.WARNING_SENTENCE, MS.WARNING_SENTENCE)

SCENARIOS: dict[str, Scenario] = {s.id: s for s in [
    _s("parcel-fee", "Parcel fee", [r"\b(?:parcel|package|delivery|courier|redeliver\w*|customs|colis)\b", r"\b(?:fee|pay|charge|settle|r[ée]glez)\b|[$€£]\s?\d", r"\b(?:on hold|held|could ?n[o']t be delivered|failed delivery|incomplete address|unpaid|en attente|clear (?:the )?customs|western union)\b", r"\b(?:confirm|update) your address\b|https?://|\b\S+\.(?:xyz|top|click|info|com|net)\b"]),
    _s("bank-security", "Bank security alert", [r"\b(?:bank|account|card)\b", r"\b(?:suspicious|unusual|locked|frozen|blocked|compromised|unauthori[sz]ed|limited|closed|fraud (?:department|team))\b", r"\b(?:verify|confirm|secure|unlock|sign in|log in|safe account|move (?:your )?(?:money|savings|balance))\b", r"https?://|\b\S+\.(?:xyz|top|click|info|com|net)\b|\bcall\b|\bcode\b|\bsecure account\b"], must=(1,)),
    _s("family-emergency", "Family emergency", [r"\b(?:mum|mom|dad|grandma|grandpa|nan|nana|gran|son|daughter|love|it'?s me)\b", r"\b(?:new (?:number|phone)|lost my|dropped my phone|stolen|broke|hospital|jail|accident|arrested|stuck|border|bail|detain)\w*", r"(?:\b(?:send|transfer|wire|pay|gift ?cards?)|\$\d)", r"\b(?:don'?t (?:tell|call)|secret|right now|hurry|asap|by \d|at once|today)\b"], must=(2,)),
    _s("tech-support", "Tech support", [r"\b(?:virus|compromised|infected|error codes?|hacked|security alert|support|technician|engineer|suspicious logins?)\b", r"\b(?:microsoft|apple|windows|computer|pc|router|internet provider|laptop|line|icloud)\b", r"\b(?:call|install|remote|anydesk|teamviewer|quicksupport|connect to your (?:screen|computer)|remote access|let our agent)\b"]),
    _s("romance", "Romance / trust", [r"\b(?:love|lonely|darling|dear friend|soldier|army|widow\w*|trust you|know you better|connection|investor)\b", r"\b(?:never met|online|deployed|overseas|abroad|stationed|oil rig|engineer|on the app|private (?:trading )?group)\b", r"(?:\b(?:send|customs|leave papers|ticket|gift ?card|bitcoin|bank details|whatsapp|telegram|start with a small amount|show you how)\b|need \$|steady \d+ ?(?:%|percent))"]),
    _s("investment", "Fake investment", [r"\b(?:invest\w*|trading|crypto|token|returns?|profit|signals?|forex|presale|usdt|eth)\b", r"(?:\b(?:guaranteed|\d+x|risk[- ]free|no risk|early backers?|limited|made \d|steady|private (?:trading )?group)|\d{1,}%|\d+ percent)", r"\b(?:deposit|transfer|send|wallet|join|start|invest|add funds|withdraw\w*)\b"]),
    _s("job-task", "Fake job / tasks", [r"\b(?:job|hiring|work from home|tasks?|earn|per day|a day|commission|data entry|resume|recruit\w*|role|position|vacanc\w*|salary|paying)\b", r"(?:\b(?:no experience|simple|easy|part[- ]time|remote (?:role|work|position))\b|\$\d[\d,]* (?:a|per) (?:day|task|hour|week)|\d+ minutes a day|\ba week\b)", r"\b(?:deposit|top up|recharge|activate|unlock|fee|reply yes|whatsapp|telegram|add me on|message me on)\b"]),
    _s("prize-lottery", "Prize / lottery", [r"\b(?:congratulations|congrats|you(?:'ve| have)? (?:won|been selected)|winner|selected|prize|lottery|reward|pre-?approved)\b", r"\b(?:claim|collect|redeem|receive|release|approved)\b", r"(?:\b(?:fee|shipping|tax|insurance|pay|gift ?card|bit\.ly)\b|[$€£]\s?\d|https?://)"]),
    _s("tax-government", "Tax / government threat", [r"\b(?:irs|tax(?:es)?|hmrc|social security|medicare|government|court|warrant|police|officer|detective|crime unit|agency|arrest|fine|toll|parking|aadhaar)\b", r"\b(?:unpaid|overdue|owe|debt|refund|suspended|blocked|penalty|summons|violation|laundering|back taxes|demand|fraud case|investigation|identity|illegal)\b", r"\b(?:pay|call|press 1|verify|gift ?cards?|prepaid|immediately|today|within \d+|otp|link|stay on the line|do not tell)\b|https?://"]),
    _s("subscription-renewal", "Subscription / purchase call-back", [r"\b(?:renew\w*|subscription|membership|prime|netflix|antivirus|norton|mcafee|geek squad|apple id|purchase|order)\b", r"(?:[$€£]\s?\d|\b(?:charged|billed|auto-?renew)\b)", r"\b(?:call|cancel|refund|dispute)\b|\b1[- ]?8\d\d\b"]),
    _s("billing-update", "Billing update link", [r"\b(?:netflix|spotify|prime|apple|microsoft|subscription|membership|billing|payment)\b", r"\b(?:payment (?:failed|declined)|update (?:your )?(?:billing|payment)|card (?:expired|declined)|billing details)\b", r"https?://|\b\S+\.(?:xyz|top|click|info)\b|\blogin\b"], must=(1,)),
    _s("overpayment", "Accidental payment", [r"\b(?:accidentally|mistakenly|by mistake|wrong account)\b", r"\b(?:sent|transferred|deposited|paid|refunded|credited)\b", r"\b(?:send (?:it )?back|return|refund|reverse)\b"]),
    _s("inheritance-advance-fee", "Inheritance / loan fee", [r"\b(?:inherit\w*|estate|unclaimed|next of kin|beneficiary|million|funds|grant|loan|approved)\b", r"\b(?:lawyer|barrister|banker|soldier|partner|trustworthy|no credit check|pre-?approved|government)\b", r"\b(?:fee|tax|insurance|processing|admin|deposit|bank details)\b"]),
    _s("account-verification", "Account verification", [r"\b(?:account|mailbox|password|email|storage|whatsapp|microsoft|google|apple id)\b", r"\b(?:verify|confirm|update|restore|upgrade|click|sign in|log in|block it|tell us)\b", r"\b(?:deactivated|suspended|closed|deleted|compromised|almost full|is full|violat\w+|within \d+|in \d+ hours|immediately|final warning|locked|blocked|unauthori[sz]ed|suspicious|fraudulent|failed login)\b", r"https?://|\b\S+\.(?:xyz|top|click|info|com|net)\b|\b(?:otp|code|password)\b"], must=(2,)),
    _s("utility-bill", "Overdue bill", [r"\b(?:electricity|power|gas|water|phone bill|internet bill|mobile|utility)\b", r"\b(?:overdue|unpaid|cut off|disconnect\w*|final notice)\b", r"\b(?:pay|call|immediately|today|https?://|gift ?card|itunes)\b"]),
    _s("boss-gift-card", "Boss asks for gift cards", [r"\b(?:boss|manager|ceo|director|colleague|it's me)\b", r"\b(?:gift ?cards?|vouchers?|itunes|google play)\b", r"\b(?:meeting|busy|urgent|don'?t call|quick favou?r|surprise|clients?|send me the (?:codes?|numbers?))\b"]),
    _s("marketplace-code", "Marketplace code request", [r"\b(?:selling|buyer|listing|item|sofa|marketplace|your ad)\b", r"\b(?:code|verify|verification|protection)\b", r"\b(?:read it|read them|send me|share|sending you|text)\b"], must=(1,)),
    _s("cheque-overpayment", "Cheque / refund-the-difference", [r"\b(?:cheque|check|money order)\b", r"\b(?:refund|send back|balance|difference|vendor|approved vendor)\b", r"\b(?:equipment|supplies|home office|babysitter|out of town|buy|deposit)\b"]),
    _s("rental-deposit", "Rental deposit", [r"\b(?:flat|apartment|property|keys|listing|owner|landlord|bedroom)\b", r"\b(?:abroad|overseas|out of (?:town|the country)|cannot show|can'?t show|post you the keys|work abroad)\b", r"\b(?:deposit|transfer|holding|pay|send)\b"]),
    _s("government-rebate", "Government rebate / refund", [r"\b(?:rebate|refund|forgiveness|grant|entitled|eligible|qualify|due a)\b", r"\b(?:government|hmrc|irs|council|federal|medicare|tax|energy|student loan)\b", r"\b(?:claim|apply|submit|confirm|bank details|programme closes|closes)\b|https?://"], must=(1,)),
    _s("ticket-prepay", "Ticket pre-payment", [r"\btickets?\b", r"\b(?:sold[- ]out|spare|face value|can'?t go)\b", r"\b(?:payment first|pay first|upfront|before|transfer|clears|once it clears)\b"]),
    _s("charity-appeal", "Charity appeal", [r"\b(?:donat\w+|victims|relief|appeal|help the)\b", r"\b(?:send what you can|every donation|cashapp|gift card|bitcoin|wire)\b", r"\b(?:code|message me|dm me|link|https?://)\b"]),
    _s("claim-approved", "Approved claim / loan", [r"\b(?:claim|loan|refund|application|subsidy|grant|insurance|rebate)\b", r"\b(?:approved|accepted|successful|selected|eligible|processed|pre-?approved)\b", r"\b(?:contact us|reply|confirm|submit|send (?:your )?documents|finali[sz]e|click|call us|respond)\b"], must=(1,)),
    _s("warranty-callback", "Warranty call-back", [r"\b(?:warranty|extended|vehicle|car)\b", r"\b(?:expire|expiring|final notice|last chance|offer ends|about to)\b", r"\b(?:press 1|call|speak to|agent)\b"]),
]}


for _id, _label, _signs, _min, _must in ZH.NEW_SCENARIOS:  # scripts that mostly exist in Chinese-language scams
    SCENARIOS[_id] = Scenario(_id, _label, tuple(Dual(None, p) for p in _signs), _min, _must)


# Neighbouring scripts are not a real disagreement (a toll notice is 'tax' to one reader and 'billing' to another).
FAMILIES = {
    "payment-notice": {"parcel-fee", "subscription-renewal", "billing-update", "utility-bill", "tax-government", "overpayment"},
    "account-alert": {"bank-security", "account-verification", "tech-support", "marketplace-code"},
    "relationship": {"family-emergency", "romance", "boss-gift-card"},
    "windfall": {"prize-lottery", "inheritance-advance-fee", "investment", "job-task", "warranty-callback"},
}


for _id, _fam in ZH.SCENARIO_FAMILY.items():
    FAMILIES[_fam].add(_id)


def same_family(a: str, b: str) -> bool:
    return a == b or any(a in f and b in f for f in FAMILIES.values())


def detect(text: str) -> tuple[str, int, str]:
    """Best-matching script: (id, signs matched, quote of the first sign) or ("", 0, "")."""
    text = NEGATED.sub(" ", text)
    best: tuple[str, int, str] = ("", 0, "")
    for sc in SCENARIOS.values():
        res = [p.search(text) for p in sc.signals]
        hits = [m for m in res if m]
        if len(hits) >= sc.min and all(res[i] for i in sc.must) and len(hits) > best[1]:
            best = (sc.id, len(hits), hits[0].group(0)[:80])
    return best
