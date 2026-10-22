"""Finding links that were written to dodge a filter, or spoken aloud.

`deobfuscate(text)` returns a cleaned COPY of a message in which hxxp://, [.], (dot), full-width dots, "\\." escapes, zero-width characters and a
few spaced-out domains are written normally, so the link finder sees them. The original text is never changed: it is the evidence and what the
user sees. Writing a link this way is NOT a scam signal on its own (security researchers and careful people do it on purpose), so nothing here
adds evidence; the hosts found simply join the others.

`from_speech(text)` turns what a speech model hears ("dhl dash fee dash pay dot x y z slash track") into a link ("dhl-fee-pay.xyz/track")."""
from __future__ import annotations

import re

from core.domain import privacy

from .knowledge import SHORTENERS

# Top-level domains a spoken or spaced-out link may end in: the ones scam links use plus the common ones (the same set the link finder knows).
TLDS = ("com", "net", "org", "xyz", "top", "click", "info", "icu", "co", "io", "me", "ly", "shop", "site", "online", "cn", "cc", "tw", "hk", "vip", "my", "sg", "link", "club",
        "live", "pro", "biz", "app", "tk", "ink", "work", "buzz", "store", "cyou", "today", "gov", "edu", "uk", "us", "sbs", "cfd", "ws", "to", "gl")
_TLD = "(?:" + "|".join(sorted(TLDS, key=len, reverse=True)) + ")"

_INVISIBLE = re.compile("[​‌‍⁠﻿­]")  # zero-width space / joiners, word joiner, BOM, soft hyphen
_DOTS = re.compile(r"(?<=[A-Za-z0-9-])[。．｡](?=[A-Za-z0-9-])")  # ideographic / full-width / half-width ideographic full stop between letters of a name
_HXXP = re.compile(r"\bh[xX*]{2}p(s?)(?=\s*(?:[:\[\(]|\s))", re.I)
# "evil[.]top" (tight), or "evil [.] top" (spaced: only when an ending follows, so a lone "[.]" or "(.)" in ordinary text is left alone)
_BRACKET_DOT = re.compile(rf"(?<=[A-Za-z0-9-])(?:[\[\(\{{](?:\.|dot)[\]\)\}}](?=[A-Za-z0-9-])|\s*[\[\(\{{]\s*(?:\.|dot)\s*[\]\)\}}]\s*(?={_TLD}\b))", re.I)
_BRACKET_SEP = re.compile(r"[\[\(\{]\s*(://|:|/)\s*[\]\)\}]")
_ESCAPED_DOT = re.compile(r"(?<=[A-Za-z0-9-])\\+\.(?=[A-Za-z0-9-])")
_SPOKEN_DOT = re.compile(rf"\b([A-Za-z0-9-]+)\s+dot\s+({_TLD})\b", re.I)
# "dhl-fee. xyz" / "dhl-fee .xyz": only for a name that already looks like a web address (a hyphen, or www), and a lower-case ending, so that the end of
# a sentence ("Reply stop. info is free", "call 0789123. today is the day") is never glued into a link.
_SPACED_DOT = re.compile(rf"\b((?:[a-z0-9]+(?:-[a-z0-9]+)+|www))(?:\s*\.\s+|\s+\.\s*)({_TLD})\b(?!-)")
_WIDE_URL_PUNCT = {"：": ":", "／": "/", "－": "-", "＿": "_", "？": "?", "＆": "&", "＝": "=", "％": "%", "＃": "#"}
_WIDE_IN_URL = re.compile(r"(?<=[A-Za-z0-9/])[：／－＿？＆＝％＃]+(?=[A-Za-z0-9/])")


def _wide_ascii(s: str) -> str:
    """Full-width letters and digits (ｄｈｌ．ｃｏｍ) are written as ordinary ones; the rest of Chinese punctuation is left alone."""
    out = []
    for c in s:
        o = ord(c)
        if 0xFF10 <= o <= 0xFF19 or 0xFF21 <= o <= 0xFF3A or 0xFF41 <= o <= 0xFF5A:
            out.append(chr(o - 0xFEE0))
        else:
            out.append(c)
    return "".join(out)


def deobfuscate(text: str) -> str:
    """A cleaned copy of `text` for finding links in. Identical to `text` when nothing was disguised."""
    s = _INVISIBLE.sub("", text)
    if re.search(r"[＀-￯。｡]", s):
        s = _wide_ascii(s)
        s = _DOTS.sub(".", s)
        s = _WIDE_IN_URL.sub(lambda m: "".join(_WIDE_URL_PUNCT.get(c, c) for c in m.group(0)), s)
    s = _BRACKET_SEP.sub(lambda m: m.group(1), s)
    s = _HXXP.sub(lambda m: "http" + m.group(1), s)
    s = _BRACKET_DOT.sub(".", s)
    s = _ESCAPED_DOT.sub(".", s)
    if re.search(r"\bdot\b", s, re.I):  # (cheap guards: the patterns below are the slow ones, and most messages have nothing for them to do)
        s = _SPOKEN_DOT.sub(lambda m: m.group(0) if m.group(1).lower() in _SPOKEN_STOP | {"polka"} else f"{m.group(1)}.{m.group(2)}", s)
    if re.search(r"\.\s|\s\.", s):
        s = _SPACED_DOT.sub(lambda m: f"{m.group(1)}.{m.group(2)}", s)
    return s


# ---------------------------------------------------------------- finding links
# A short link written without "https://" ("rb.gy/Ab3x") is still a link. The general link finder only knows bare names ending in common domains, so the
# shorteners get their own pattern (a path is required: a bare mention of "bit.ly" is not a link to anywhere).
SHORT_URL_RE = re.compile(r"(?<![A-Za-z0-9@.-])(?:" + "|".join(re.escape(h) for h in sorted(SHORTENERS, key=len, reverse=True)) + rf")/[^{privacy._NOT_URL}]+", re.I)
_TRAILING = ".,;:!?)]}>'\"”’"


def find(text: str, email_spans: list[tuple[int, int]] | None = None) -> list[tuple[str, str]]:
    """[(host, url as written)] for every link in the text, in order, one per distinct link. An email address is not a link to its domain."""
    spans = email_spans or []
    found: dict[int, tuple[int, str]] = {}
    for rx in (privacy.URL_RE, SHORT_URL_RE):
        for m in rx.finditer(text):
            if any(a <= m.start() < b for a, b in spans) or any(s <= m.start() < e for s, (e, _u) in found.items() if s != m.start()):
                continue  # inside an email address, or inside a link already found ("http://bit.ly/x" is one link, not two)
            found.setdefault(m.start(), (m.end(), m.group(0)))
    out, seen = [], set()
    for start in sorted(found):
        if any(s < start < e for s, (e, _u) in found.items()):
            continue
        url = found[start][1].rstrip(_TRAILING)
        host = privacy.host_of(url)
        if url and (host, url) not in seen:
            seen.add((host, url))
            out.append((host, url))
    return out


# ---------------------------------------------------------------- speech
_DIGITS = {"zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9"}
_DASH = {"dash", "hyphen", "minus"}
_SPOKEN_STOP = {"the", "a", "an", "of", "in", "on", "to", "my", "your", "our", "this", "that", "it", "is", "and", "or", "for", "with", "at", "by", "from", "as", "i", "we", "you",
                "he", "she", "they", "no", "not", "any", "some", "com"}  # "the dot com bubble" is not a link
_WORD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def _clean_tok(tok: str) -> str:
    """A token as a speech model writes it ("X.", "y,", "D.H.L.") reduced to what was said, lower-case."""
    t = tok.lower().strip(",;!?\"'()")
    if re.fullmatch(r"(?:[a-z0-9]\.)+[a-z0-9]?", t):
        return t.replace(".", "")
    return t.rstrip(".")


def _is_char(t: str) -> bool:
    return (len(t) == 1 and t.isalnum() and t.isascii()) or t in _DIGITS


def _char(t: str) -> str:
    return _DIGITS.get(t, t)


def _label(toks: list[str], i: int, step: int) -> tuple[str, int] | None:
    """The name part ending just before (step=-1) or starting at (step=+1) position `i`: either one word ("dhl", "fee-pay") or spelled-out letters and digits
    ("x y z", "one two three"). Returns (text, how many tokens used)."""
    j = i
    if not (0 <= j < len(toks)):
        return None
    t = toks[j]
    if _is_char(t):
        run = []
        while 0 <= j < len(toks) and _is_char(toks[j]) and len(run) < 24:
            run.append(_char(toks[j]))
            j += step
        if step < 0:
            run.reverse()
        return "".join(run), len(run)
    if _WORD.fullmatch(t) and t not in _DASH and t != "dot" and t != "slash":
        return t, 1
    return None


def _tld_at(toks: list[str], i: int) -> tuple[str, int] | None:
    """A top-level domain starting at token i: one token ("com") or spelled out ("c o m")."""
    if i >= len(toks):
        return None
    if toks[i] in TLDS:
        return toks[i], 1
    run = []
    for j in range(i, min(i + 6, len(toks))):
        if not (len(toks[j]) == 1 and toks[j].isalpha()):
            break
        run.append(toks[j])
        if "".join(run) in TLDS and (j + 1 >= len(toks) or not (len(toks[j + 1]) == 1 and toks[j + 1].isalpha())):
            return "".join(run), len(run)
    return None


def _spoken_link(toks: list[str], dot_at: int) -> tuple[int, int, str] | None:
    """Build the link around the "dot" at `dot_at` that is followed by a top-level domain. Returns (first token, one past the last token, link)."""
    parts: list[str] = []  # the host, built right to left: labels joined by "." and "-"
    # left: label (dash label)* (dot label (dash label)*)*, as far back as the pattern keeps going
    lab = _label(toks, dot_at - 1, -1)
    if lab is None or lab[0] in _SPOKEN_STOP:
        return None
    parts.append(lab[0])
    start = dot_at - lab[1]
    while start - 1 >= 0 and (toks[start - 1] in _DASH or toks[start - 1] == "dot"):
        sep = "-" if toks[start - 1] in _DASH else "."
        more = _label(toks, start - 2, -1)
        if more is None:
            break
        parts.append(sep)
        parts.append(more[0])
        start = start - 1 - more[1]
    host = "".join(reversed(parts))
    # optional scheme before the name: "h t t p s colon slash slash" / "https colon slash slash"
    scheme = ""
    k = start
    if k >= 3 and toks[k - 1] == "slash" and toks[k - 2] == "slash" and toks[k - 3] == "colon":
        k -= 3
        for cand in ("https", "http"):
            if k - 1 >= 0 and toks[k - 1] == cand:
                scheme, k = cand + "://", k - 1
                break
            n = len(cand)
            if k - n >= 0 and toks[k - n:k] == list(cand):
                scheme, k = cand + "://", k - n
                break
        if not scheme:
            k = start
    first = k if scheme else start
    tld = _tld_at(toks, dot_at + 1)
    if tld is None:
        return None
    link = scheme + host + "." + tld[0]
    end = dot_at + 1 + tld[1]
    # optional path: "slash track", "slash a b c", "dot html"
    n_parts = 0
    while end < len(toks) and toks[end] == "slash" and n_parts < 6:
        link += "/"
        end += 1
        if end < len(toks) and toks[end] in ("slash",):
            continue
        seg = _label(toks, end, +1)
        if seg is None:
            break
        link += seg[0]
        end += seg[1]
        while end + 1 < len(toks) and toks[end] in _DASH:
            more = _label(toks, end + 1, +1)
            if more is None:
                break
            link += "-" + more[0]
            end += 1 + more[1]
        if end + 1 < len(toks) and toks[end] == "dot":
            ext = _label(toks, end + 1, +1)
            if ext is not None:
                link += "." + ext[0]
                end += 1 + ext[1]
        n_parts += 1
    return first, end, link


def from_speech(text: str) -> str:
    """Write a link that was spoken the way people say it ("dhl dash fee dash pay dot x y z slash track") as a link ("dhl-fee-pay.xyz/track").
    Text with no spoken "dot <ending>" in it comes back unchanged."""
    if not re.search(r"\bdot\b", text, re.I):
        return text
    raw = text.split()
    toks = [_clean_tok(t) for t in raw]
    out: list[str] = []
    i = 0
    covered_until = 0
    # find the spoken links, left to right, without overlapping
    spans: list[tuple[int, int, str]] = []
    for d, t in enumerate(toks):
        if t != "dot" or d < covered_until:
            continue
        found = _spoken_link(toks, d)
        if found and found[0] >= covered_until:
            spans.append(found)
            covered_until = found[1]
    if not spans:
        return text
    for first, end, link in spans:
        out.extend(raw[i:first])
        tail = re.search(r"[.,;:!?)]+$", raw[end - 1])  # the sentence's own punctuation stays after the link
        out.append(link + (tail.group(0) if tail else ""))
        i = end
    out.extend(raw[i:])
    return " ".join(out)
