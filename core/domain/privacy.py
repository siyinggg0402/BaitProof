"""Deterministic PII handling shared by storage (what we keep) and the model client (what we send)."""
from __future__ import annotations

import re
from urllib.parse import urlparse

_NOT_URL = r"\s\u2e80-\u9fff\u3000-\u303f\uff00-\uffef"  # whitespace, Chinese characters and full-width punctuation end a link (Chinese is written without spaces)
URL_RE = re.compile(rf"(?:https?://|www\.)[^{_NOT_URL}]+|(?<![a-z0-9-])[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|net|org|xyz|top|click|info|icu|co|io|me|ly|shop|site|online|cn|cc|tw|hk|vip|my|sg|link|club|live|pro|biz|app|tk|ink|work|buzz|store|cyou|today)(?![a-z0-9-])(?:/[^{_NOT_URL}]*)?", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{6,}\d")
LONG_DIGITS_RE = re.compile(r"\d{9,}")  # account / card style numbers
ID_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?![\dA-Za-z])")  # a mainland-China resident ID number (18 characters, the last may be X)
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
TIME_RANGE_RE = re.compile(r"\d{1,2}[.:]\d{2}\s?[-–]\s?\d{1,2}[.:]\d{2}")  # "09.00-11.00": how Indonesian and Malay write opening hours and slots, not a phone number


def host_of(url: str) -> str:
    u = url if "//" in url else "//" + url
    return (urlparse(u).hostname or url).lower().rstrip(".,)")


def redact(text: str, links: bool = True) -> str:
    """URLs shrink to bare host (scam domains aren't personal; paths/tokens may be); emails and phone numbers go."""
    text = EMAIL_RE.sub("[email]", text)
    text = URL_RE.sub(lambda m: host_of(m.group(0)), text)
    text = ID_RE.sub("[number]", text)
    text = PHONE_RE.sub("[number]", text)
    return text.strip()


def phone_matches(text: str) -> dict[str, str]:
    """{normalised digits: raw text as written} for phone-like numbers. For LOCAL checks and quoting only; never sent anywhere."""
    out: dict[str, str] = {}
    for m in PHONE_RE.finditer(text):
        raw = m.group(0).strip()
        if DATE_RE.fullmatch(raw) or TIME_RANGE_RE.fullmatch(raw):
            continue
        digits = re.sub(r"\D", "", raw)
        if 7 <= len(digits) <= 15:
            out.setdefault(("+" if raw.startswith("+") else "") + digits, raw)
    return out


def phones_in(text: str) -> list[str]:
    return list(phone_matches(text))


def scrub_outgoing(text: str) -> tuple[str, int]:
    """Last line of defence before text leaves for a model: remove anything personal that slipped through.
    Returns (clean text, number of things removed). A non-zero count means an upstream redaction was missed."""
    n = 0

    def bump(sub: str):
        def f(m):
            nonlocal n
            n += 1
            return sub
        return f

    text = EMAIL_RE.sub(bump("[email]"), text)
    text = ID_RE.sub(bump("[number]"), text)
    text = PHONE_RE.sub(bump("[number]"), text)
    text = LONG_DIGITS_RE.sub(bump("[number]"), text)
    return text, n
