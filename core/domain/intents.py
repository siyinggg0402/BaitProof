"""The closed catalogue of message PURPOSES. The model must choose from this list (never invent one), and every choice is validated
against cues in the text. Each entry says what a genuine message of that kind looks like and what its scam version looks like, and
that guidance is fed to the analysis prompt, so the model judges against a definition instead of improvising.

risk:      benign  = ordinary, expected message types      risky = purposes that ask the reader to give something up
clearable: True = a deterministic check can vouch for it WITHOUT the model (only when nothing risky is present)"""
from __future__ import annotations

import re
from dataclasses import dataclass

from core.lang import ms as MS
from core.lang import zh as ZH
from core.lang.text import Dual


@dataclass(frozen=True)
class Purpose:
    id: str
    label: str
    risk: str  # benign | neutral | risky
    genuine: str  # what a real one looks like
    scam: str  # what the scam version looks like
    cues: Dual | None = None  # text must contain one of these for the purpose to be valid (English cues plus their Chinese twin)
    clearable: bool = False


def _p(id, label, risk, genuine, scam, cues=None, clearable=False) -> Purpose:
    return Purpose(id, label, risk, genuine, scam, Dual(cues, ZH.PURPOSE_CUES.get(id), MS.PURPOSE_CUES.get(id)) if cues else None, clearable)


PURPOSES: dict[str, Purpose] = {p.id: p for p in [
    # ---- ordinary message types
    _p("social-chat", "casual chat", "benign", "people who know each other talking: plans, jokes, check-ins, small favours",
       "a stranger posing as a friend or relative; a sudden money or code request; a 'new number' story"),
    _p("appointment-booking", "appointment or booking", "benign", "a reminder or confirmation of a visit, table, viewing or service slot; nothing to pay",
       "a 'reschedule' that sends you to a link or a phone number you don't know, or asks for a deposit",
       r"\b(?:appointment|booking|booked|reservation|reminder|reschedul\w+|table for|viewing|check-?in|session|slot|confirmed?)\b", True),
    _p("delivery-update", "delivery update", "benign", "your order, parcel or ride is on its way or has arrived; no fee and no unknown link",
       "a parcel 'delayed' or 'on hold' that tells you to track, pay a small fee or update your address through a link",
       r"\b(?:order|parcel|package|delivery|delivered|dispatched|shipped|courier|arriv\w+|tracking|ride|driver)\b", True),
    _p("transaction-alert", "payment or account alert", "neutral", "tells you a payment happened or a statement is ready and says to use the number on your card or the official app",
       "an ALARM about your card or account (blocked, hacked, unauthorised, suspicious activity) that tells you to act: verify, reactivate, change a password, open an app, call a number, give a PIN; or a 'payment authorised' alert with a number to call",
       r"\b(?:payment|purchase|transaction|debit|credit|statement|balance|paid|received|charged|card ending|spent)\b"),
    _p("one-time-code", "login code", "benign", "delivers a code the reader just asked for and says not to share it",
       "asks you to reply with, read out or submit the code, or arrives when you asked for nothing",
       r"\b(?:otp|code|passcode|pin|verification)\b[^.!?\n]{0,30}\b\d{3}[\s-]?\d{3,5}\b|\b\d{4,8}\b[^.!?\n]{0,20}\b(?:is|as) your\b", True),
    _p("account-notice", "account notice", "neutral", "a routine notice: password changed, new sign-in, plan renewal; asks for nothing",
       "claims your account, plan or data is in trouble (hacked, full, expiring) and tells you to act now: verify, renew, secure it, change your password",
       r"\b(?:account|password|sign-?in|logged in|login|subscription|membership|plan|renews?)\b"),
    _p("work-logistics", "work, school or club logistics", "benign", "a meeting moved, a form due, a rota or event detail from someone in your group",
       "an 'HR' or 'boss' message that asks you to reply urgently, buy cards or keep it quiet",
       r"\b(?:meeting|team|standup|office|class|school|club|rota|shift|homework|form|committee|practice|training|event|agenda|attached|bin|recycling)\b"),
    _p("invoice-or-bill", "invoice or bill", "neutral", "a bill or invoice for something you really have, paid through your usual channel",
       "an invoice you don't recognise, changed bank details, or a threat of disconnection unless you pay now",
       r"\b(?:invoice|bill|statement|amount due|due on|payment due|balance due|rent)\b"),
    _p("marketing-offer", "advert or offer", "neutral", "a shop or service you use promoting a sale; easy to ignore or opt out of",
       "a 'claim your reward / cashback' or 'limited time' push, an offer too good to be true, or one that charges you per message or per minute",
       r"\b(?:offer|sale|discount|% off|deal|promo|coupon|exclusive|subscribe|unsubscribe)\b"),
    # ---- purposes that ask the reader to give something up
    _p("request-payment", "request for money", "risky", "someone you know and can verify asking for a small amount for a reason you can check",
       "a fee, deposit, tax or 'refund the difference' before you receive anything; gift cards, crypto, wire or a new account"),
    _p("request-secret", "request for a code, password or personal detail", "risky", "essentially never: real organisations don't ask for these by message",
       "asks you to send, read out or type a code, PIN, password, ID number, date of birth or bank details"),
    _p("request-install-access", "request to install an app or allow access", "risky", "essentially never unsolicited",
       "'support' asks you to install remote-control software or let an agent connect to your computer",
       r"\b(?:install|download|anydesk|teamviewer|remote|connect to your|let (?:our|the) agent|screen)\b"),
    _p("claim-prize-reward", "prize, reward or refund to claim", "risky", "a prize or refund you really entered for or are owed, with no fee",
       "a prize, grant, rebate, loan or reward you never applied for, with a fee, code or short-code reply to 'claim' it",
       r"\b(?:won|winner|prize|reward|claim|selected|lottery|jackpot|refund|rebate|grant|subsidy|bonus|voucher|free|approved|eligible|entitled)\b"),
    _p("offer-job-or-investment", "job, loan or investment offer", "risky", "an advertised role you applied for; a regulated provider you contacted",
       "easy money: high pay for simple tasks, guaranteed returns, no-credit-check loans, a recruiter on Telegram",
       r"\b(?:job|role|position|hiring|recruit\w*|vacanc\w*|salary|earn\w*|(?:a|per) (?:day|week|hour|task)|tasks?|commission|invest\w*|trading|crypto\w*|returns?|profit\w*|loan|forex)\b"),
    _p("urgent-account-warning", "urgent warning about a problem", "risky", "rare; real providers send letters, give time, and point to their own app or the number on your card",
       "your account, parcel, bill or legal status is 'in trouble' and you must click, call or pay right now",
       r"\b(?:suspended|locked|blocked|compromised|unauthori[sz]ed|suspicious|fraud\w*|violation|deactivat\w+|expire[sd]?|overdue|failed|warrant|arrest\w*|disconnect\w*|final notice|immediately|urgent)\b"),
    _p("first-contact-opener", "out-of-the-blue first contact", "risky", "rare: a real person with real context (who they are, why they wrote)",
       "'is this X?', 'wrong number', 'new number', 'I saw your profile or listing', 'can you check you can receive a message', 'add me on Telegram'"),
    _p("emotional-plea", "emergency or emotional appeal", "risky", "someone you know and can reach, in a real situation you can confirm by phoning them",
       "a relative or new friend in sudden trouble who says not to call or tell anyone and needs money now",
       r"\b(?:trouble|stuck|hospital|accident|arrested|please help|desperate|lonely|love|miss you|don'?t tell|secret|emergency|bail|favou?r)\b"),
    _p("callback-request", "request to call a number", "risky", "the number is one you already know, or on the back of your card",
       "a charge, order or 'security issue' you don't recognise, with a number to call to cancel or dispute it"),
    _p("other", "something else", "neutral", "anything that fits none of the above", "n/a"),
]}

NEEDS_PROOF = {"marketing-offer", "transaction-alert", "invoice-or-bill", "account-notice"}  # copied by scams so often that "safe" needs independent confirmation
PRIORITY_RISKY = ["request-secret", "request-install-access", "request-payment", "claim-prize-reward", "offer-job-or-investment", "urgent-account-warning",
                  "emotional-plea", "first-contact-opener", "callback-request"]
PRIORITY_NORMAL = ["one-time-code", "delivery-update", "appointment-booking", "transaction-alert", "invoice-or-bill", "account-notice",
                   "work-logistics", "marketing-offer", "social-chat", "other"]


def valid(pid: str) -> bool:
    return pid in PURPOSES


def catalogue_prompt() -> str:
    """The list the model must choose from: one line per purpose."""
    return "\n".join(f"- {p.id}: {p.label}" for p in PURPOSES.values())


def guidance(pid: str) -> str:
    p = PURPOSES.get(pid)
    if p is None or pid == "other":
        return ""
    return f"{p.label} ({p.id}). A GENUINE one: {p.genuine}. The SCAM version: {p.scam}."


# ---- what a deterministic check must see before it may vouch for a message WITHOUT the model. Deliberately much stricter than `cues`:
# the cues decide what a message is ABOUT; these decide whether it is plainly ordinary.
_NEGATIVE = Dual(r"\b(?:fee|pay|payment|claim|win|won|winner|prize|reward|free|delayed|held|on hold|failed|unpaid|track now|verify|confirm your|"
                       r"update your|click|link|reply|send|text|txt|call|urgent|immediately|suspend\w*|locked|expire[sd]?|"
                       r"go ?to|download\w*|subscri\w+|wap|service menu|mobile internet|content|ringtone|tones?)\b", ZH.NEGATIVE, MS.NEGATIVE)
_SPLIT_URL = re.compile(r"\b\w{2,}\.\s\w{1,}\.?\s?(?:tv|com|net|org|info|biz|mobi|xyz|co|uk|me)\b|\b\w+\.\s(?:tv|com|net|org|info|biz|mobi|xyz)\b", re.I)  # "wap. bangb. tv": a web address broken up to dodge link detection
_STATUS = Dual(r"\b(?:has|have|been|is|are|was|will be)\b[^.!?]{0,30}\b(?:shipped|dispatched|delivered|arriv\w+|out for delivery|on (?:its|the) way|ready (?:for|to) collect\w*)\b", ZH.STATUS, MS.STATUS)
_TIME = Dual(r"\b\d{1,2}(?::\d{2})?\s?(?:am|pm)\b|\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|today|tonight|next week)\b", ZH.TIME, MS.TIME)
_APPT = Dual(r"\b(?:appointment|booking|booked|reservation|table for|viewing)\b", ZH.APPT, MS.APPT)
_CODE_REQ = Dual(r"\b(?:reply|send|text|read|share|give|enter|submit|provide|call|click|verify)\b", ZH.CODE_REQ, MS.CODE_REQ)
_WARNING = Dual(r"[^.!?\n]*\b(?:never|do not|don'?t|not) share[^.!?\n]*[.!?]?", ZH.WARNING_SENTENCE, MS.WARNING_SENTENCE)
_APPT_NEGATIVE = Dual(r"\b(?:fee|deposit|pay|payment|claim|win|prize|free|urgent|immediately)\b", ZH.APPT_NEGATIVE, MS.APPT_NEGATIVE)


def clearing_conditions_met(pid: str, text: str, asks: set) -> bool:
    """True only when the message is plainly an ordinary instance of a clearable purpose."""
    if pid == "one-time-code":
        # delivers a code and asks for nothing; a warning not to share it is fine, any request to send or read it back is not
        body = _WARNING.sub(" ", text)
        return not asks and not _CODE_REQ.search(body)
    if pid == "delivery-update":
        return not asks and bool(_STATUS.search(text)) and not _NEGATIVE.search(text) and not _SPLIT_URL.search(text)
    if pid == "appointment-booking":
        return not (asks - {"reply"}) and bool(_APPT.search(text)) and bool(_TIME.search(text)) and not _APPT_NEGATIVE.search(text)
    return False
