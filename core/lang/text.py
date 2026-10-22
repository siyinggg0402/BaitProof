"""Which language is a message in, and how to write one Chinese pattern that matches both scripts.

Chinese has no word boundaries (so no \\b) and two scripts (Simplified and Traditional). `Z()` takes a pattern written in Simplified and
returns one that also matches the Traditional forms, so each rule is written once. The character table (zh_t2s.json) comes from the
OpenCC project's TSCharacters.txt (Apache-2.0), restricted to one-to-one common characters so text length never changes."""
from __future__ import annotations

import contextvars
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

_T2S: dict[str, str] = json.loads((Path(__file__).parent / "data" / "zh_t2s.json").read_text(encoding="utf-8"))
_S2T: dict[str, str] = {}
for _t, _s in _T2S.items():
    _S2T[_s] = _S2T.get(_s, "") + _t

CJK = re.compile(r"[一-鿿]")
_KANA = re.compile(r"[぀-ヿ]")
_HANGUL = re.compile(r"[가-힯]")
_SCRIPTS = {  # non-Latin scripts we recognise, mapped to an ISO-ish code (the model reads them; our rules do not)
    "ar": re.compile(r"[؀-ۿ]"), "hi": re.compile(r"[ऀ-ॿ]"), "bn": re.compile(r"[ঀ-৿]"),
    "ta": re.compile(r"[஀-௿]"), "th": re.compile(r"[฀-๿]"), "ru": re.compile(r"[Ѐ-ӿ]"),
}
_EN = frozenset("the and you your to is a of for in on it i we are be this that with at my me can will please have has not from or if as so by an".split())
_MS = frozenset(("yang dan anda untuk dengan di ini itu akan telah kami saya tidak atau dalam pada dari sila kod ke akaun boleh jangan sudah ada kita mereka adalah "
                 "kepada tahniah wang sebagai oleh juga lagi sahaja tolong nombor baru telefon sedang masa hari esok semua besok kamu aku udah dah nanti ya yg gak nggak "
                 "enggak ga kok sih deh kan saja banget aja bisa mau tak nak kat tu ni je la lah kau dia sampai pun pula hanya sangat sekali masih bila mana siapa kenapa "
                 "bagaimana macam perlu mesti harus ingin mahu hendak buat pergi datang balik pulang makan minum semalam tadi setiap antara hingga kerana sebab supaya agar "
                 "jika kalau apabila ketika sambil selepas sebelum selama belum pernah terima kasih selamat hadiah saudara tuan puan rekening bayar duit pinjam segera "
                 "sekarang klik pautan tautan transfer kode anda").split())
_OTHER_LATIN = {  # a few stopwords is enough to say "this is Latin script but not English or Malay"
    "es": frozenset("el la los las de que y en un una por con para su es se no lo como más pero sus".split()),
    "fr": frozenset("le la les de des et en un une du que qui pour dans est pas vous nous votre sur avec".split()),
    "de": frozenset("der die das und ist nicht ein eine zu den mit sie ich von für auf dem sich".split()),
    "pt": frozenset("o a os as de que e em um uma para com não é se do da por mais seu".split()),
}
RULES_LANGS = frozenset({"en", "zh", "zh-Hant", "ms"})  # languages our built-in rules understand (ms = Malay and Indonesian); everything else is judged by the model alone
CURRENT: contextvars.ContextVar[str] = contextvars.ContextVar("baitproof_lang", default="en")  # the language of the message being checked (set by ingest)


def is_traditional_char(c: str) -> bool:
    return c in _T2S and _T2S[c] != c


@lru_cache(maxsize=2048)
def detect(text: str) -> str:
    """'en' | 'zh' (Simplified) | 'zh-Hant' (Traditional) | 'ms' (Malay / Indonesian) | 'ja' | 'ko' | 'ar' | 'hi' | ... | 'other'."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "en"
    n = len(letters)
    cjk, kana, hangul = len(CJK.findall(text)), len(_KANA.findall(text)), len(_HANGUL.findall(text))
    if hangul / n > 0.2:
        return "ko"
    if kana / n > 0.05:
        return "ja"
    if cjk and cjk / n >= 0.15:  # code-mixed messages ("【中国银行】… click http://…") still count as Chinese
        trad = sum(is_traditional_char(c) for c in CJK.findall(text))
        simp = sum(1 for c in CJK.findall(text) if c in _S2T)  # a simplified form that has a distinct traditional one
        return "zh-Hant" if trad > simp else "zh"
    for code, rx in _SCRIPTS.items():
        if len(rx.findall(text)) / n > 0.3:
            return code
    words = re.findall(r"[^\W\d_]+", re.sub(r"https?://\S+|www\.\S+|\S+@\S+|\b[\w-]+(?:\.[\w-]+)+\b", " ", text.lower()))  # links and addresses say nothing about language
    if not words:
        return "en"
    score = {"en": sum(w in _EN for w in words) / len(words), "ms": sum(w in _MS for w in words) / len(words)}
    for code, sw in _OTHER_LATIN.items():
        score[code] = sum(w in sw for w in words) / len(words)
    best = max(score, key=score.get)
    if score[best] < 0.08:
        return "en" if len(words) < 6 else "other"  # too short to tell: assume English; long and unrecognised: say so
    return best if best in ("en", "ms") else "other"


def to_simplified(s: str) -> str:
    return "".join(_T2S.get(c, c) for c in s)


def canon(s: str) -> str:
    """Comparison form for quotes: width-folded, lower-case, Traditional folded to Simplified, and (for Chinese) spacing ignored."""
    s = to_simplified(unicodedata.normalize("NFKC", s).lower())
    return re.sub(r"\s+", "", s) if CJK.search(s) else re.sub(r"\s+", " ", s).strip()


def zpat(p: str) -> str:
    """Expand each Simplified character in a pattern to a class that also holds its Traditional forms ('验证码' -> '[验驗][证證][码碼]')."""
    out, i, in_class = [], 0, False
    while i < len(p):
        c = p[i]
        if c == "\\" and i + 1 < len(p):
            out.append(p[i:i + 2])
            i += 2
            continue
        if c == "[" and not in_class:
            in_class = True
        elif c == "]" and in_class:
            in_class = False
        elif (v := _S2T.get(c)) is not None and "一" <= c <= "鿿":
            out.append(c + v if in_class else f"[{c}{v}]")
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def Z(p: str, flags: int = re.I | re.S) -> re.Pattern:
    """Compile a pattern written in Simplified so that it matches Simplified and Traditional text."""
    return re.compile(zpat(p), flags)


_LEET = str.maketrans("013457", "oieast")
_MIXED_TOKEN = re.compile(r"(?=[A-Za-z0-9]*[A-Za-z])(?=[A-Za-z0-9]*[013457])[A-Za-z0-9]+")


@lru_cache(maxsize=4096)
def deleet(text: str) -> str:
    """The same text with digit-for-letter disguises undone INSIDE words that mix letters and digits ('BL0CKED' -> 'BLOCKED', 'w0n' -> 'won').
    Same length as the input, so a match found here sits at the same place in the original. Plain numbers, phone numbers and prices are untouched."""
    return _MIXED_TOKEN.sub(lambda m: m.group(0).translate(_LEET), text)


class _Hit:
    """A match found in the de-leeted text, reading back the ORIGINAL words (so quotes stay verbatim)."""
    __slots__ = ("_m", "_src")

    def __init__(self, m, src: str) -> None:
        self._m, self._src = m, src

    def span(self, n: int = 0):
        return self._m.span(n)

    def start(self, n: int = 0) -> int:
        return self._m.start(n)

    def end(self, n: int = 0) -> int:
        return self._m.end(n)

    def group(self, n: int = 0) -> str:
        a, b = self._m.span(n)
        return self._src[a:b]


class Dual:
    """An English pattern with a Chinese twin and a Malay/Indonesian twin. The Chinese one runs only on text that contains Chinese characters, the
    Malay one only while the message being checked is detected as Malay/Indonesian, so English behaviour (and every English number we have
    measured) is untouched. Offers the same search/finditer/sub/findall a compiled pattern does."""
    __slots__ = ("en", "zh", "ms")

    def __init__(self, en: str | re.Pattern | None, zh: str | None = None, ms: str | None = None, flags: int = re.I | re.S) -> None:
        self.en = (re.compile(en, flags) if isinstance(en, str) else en)
        self.zh = Z(zh, flags) if zh else None
        self.ms = re.compile(ms, flags) if ms else None

    @property
    def pattern(self) -> str:
        return self.en.pattern if self.en is not None else ""

    def _twins(self, text: str) -> list:
        out = [self.en] if self.en is not None else []
        if self.zh is not None and CJK.search(text):
            out.append(self.zh)
        if self.ms is not None and CURRENT.get() == "ms":
            out.append(self.ms)
        return out

    def search(self, text: str, pos: int = 0):
        best = None
        for rx in self._twins(text):
            m = rx.search(text, pos)
            if m is not None and (best is None or m.start() < best.start()):
                best = m
        if best is None and (alt := deleet(text)) != text:  # scammers write "BL0CKED" and "w0n" to dodge filters; the words are still there
            for rx in self._twins(alt):
                m = rx.search(alt, pos)
                if m is not None and (best is None or m.start() < best.start()):
                    best = _Hit(m, text)
        return best

    def finditer(self, text: str):
        ms = [m for rx in self._twins(text) for m in rx.finditer(text)]
        if not ms and (alt := deleet(text)) != text:
            ms = [_Hit(m, text) for rx in self._twins(alt) for m in rx.finditer(alt)]
        return iter(sorted(ms, key=lambda m: m.start()))

    def findall(self, text: str) -> list:
        return [x for rx in self._twins(text) for x in rx.findall(text)]

    def sub(self, repl, text: str) -> str:
        for rx in self._twins(text):
            text = rx.sub(repl, text)
        return text
