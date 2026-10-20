"""Semantic grounding. The grounding gate proves a model's QUOTE exists in the message; this gate proves its CLAIM is possible.
A model asked to pick from a list of tricks will happily recite one ('the address is slightly off') for a message that has no
address at all. Every trick has something the message must contain for the claim to be true; if it doesn't, the claim is dropped."""
from __future__ import annotations

import re
from typing import Callable

from core.domain.schemas import TacticHit

from .ingest import Ingested
from .intent import Intent
from .tools import Findings

I = re.I


def _rx(p: str) -> Callable[[str], bool]:
    r = re.compile(p, I)
    return lambda t: bool(r.search(t))


_money_rail = _rx(r"\b(?:gift ?cards?|bitcoin|crypto|usdt|wire|western union|moneygram|cash ?app|zelle|venmo|prepaid|voucher|bank transfer|cheque|check|money order)\b")
_remote = _rx(r"\b(?:install|download|anydesk|teamviewer|quicksupport|remote|screen[- ]?share|support app|connect to your (?:computer|screen|pc|laptop|device)|let (?:our|the) agent|access your (?:computer|device|phone))\b")
_secret_ask = _rx(r"\b(?:reply|send|read|tell|give|share|confirm|provide|enter|submit|verify)\b[^.!?\n]{0,30}\b(?:code|otp|pin|password|passcode|date of birth|dob|card number|bank details|full name|login|ssn)\b")
_job = _rx(r"\b(?:job|role|position|hiring|recruit\w*|vacanc\w*|tasks?|earn\w*|per (?:day|week|hour|task)|a (?:day|week)|commission|work from home|remote work|employ\w*|salary|paying|income)\b")
_invest = _rx(r"\b(?:invest\w*|trading|trade|crypto\w*|bitcoin|token|returns?|profit\w*|forex|portfolio|signals?|dividends?|\d+ ?(?:%|percent))")
_fee = _rx(r"\b(?:fee|deposit|tax|charge|processing|insurance|pay|payment|transfer|send|cheque|check|balance|refund)\b")
_authority = _rx(r"\b(?:police|officer|detective|court|judge|agency|government|tax office|irs|hmrc|medicare|social security|fraud (?:team|department)|security (?:team|line|department)|investigator|barrister|lawyer|attorney|federal|council)\b")
_emotional = _rx(r"\b(?:trouble|stuck|hospital|accident|arrested|please help|desperate|lonely|love you|miss you|don'?t tell|keep (?:it )?(?:a )?secret|only you|nobody else|favou?r|connection|trust you|widow\w*)\b")
_windfall = _rx(r"\b(?:won|winner|prize|reward|selected|free|guaranteed|profit|returns?|earn\w*|bonus|jackpot|lottery|million|rebate|refund|forgiveness|grant|eligible|qualif\w+|entitled|estate|inherit\w*)\b")


def _lookalike(ing, it, f): return bool(ing.entities.hosts) and not f.all_links_official()
def _rail(ing, it, f): return bool(ing.entities.rails) or _money_rail(ing.text)
def _otp(ing, it, f): return bool(it.asks & {"share_code", "share_credentials"}) or _secret_ask(ing.text)
def _fee_ask(ing, it, f): return "pay" in it.asks or _fee(ing.text)
def _auth(ing, it, f): return it.claimed_kind == "authority" or _authority(ing.text)
def _imperson(ing, it, f): return it.claimed_kind in ("authority", "organisation") or bool(ing.entities.brands)
def _emo(ing, it, f): return bool(it.pressure_kinds & {"secrecy", "emotional", "threat"}) or it.claimed_kind == "relation" or _emotional(ing.text)
def _urgent(ing, it, f): return bool(it.pressure_kinds & {"deadline", "threat"})


# tactic id -> (what the message must contain, human reason)
PRECONDITIONS: dict[str, tuple[Callable[[Ingested, Intent, Findings], bool], str]] = {
    "lookalike-link": (_lookalike, "there is no unverified link in the message"),
    "irreversible-payment": (_rail, "no hard-to-reverse payment method is mentioned"),
    "remote-access-request": (lambda i, n, f: _remote(i.text), "nothing asks you to install or allow remote access"),
    "otp-credential-phish": (_otp, "nothing asks you for a code or personal detail"),
    "job-task-scam": (lambda i, n, f: _job(i.text), "it isn't about work or earning"),
    "investment-crypto": (lambda i, n, f: _invest(i.text), "it isn't about investing"),
    "advance-fee": (_fee_ask, "no payment or fee is involved"),
    "authority-spoofing": (_auth, "no official body is mentioned"),
    "impersonation-official": (_imperson, "the sender doesn't claim to be an organisation"),
    "emotional-manipulation": (_emo, "there is no emotional pressure or secrecy"),
    "urgency-pressure": (_urgent, "there is no deadline or threat"),
    "too-good-to-be-true": (lambda i, n, f: _windfall(i.text), "no prize, windfall or big promise is offered"),
}


def filter_claims(tactics: list[TacticHit], ing: Ingested, it: Intent, f: Findings) -> tuple[list[TacticHit], list[str]]:
    """Keep claims whose preconditions hold. Returns (kept, ['trick: why it was dropped'])."""
    kept, dropped = [], []
    for t in tactics:
        pre = PRECONDITIONS.get(t.id)
        if pre is None or pre[0](ing, it, f):
            kept.append(t)
        else:
            dropped.append(f"{t.id}: {pre[1]}")
    return kept, dropped
