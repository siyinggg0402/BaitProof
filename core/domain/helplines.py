"""Official places to get help or report a scam, for Singapore and Malaysia, in the reader's language.

Every number and address here was checked against a government page on 23 Oct 2026 (ScamShield and the Singapore Police Force for Singapore; The Star's report of
the Communications Minister, and the Royal Malaysia Police's Semak Mule portal listed on malaysia.gov.my, for Malaysia). Numbers change: re-check them before a release.
Shown when a message looks like a scam, or when someone says they have already paid or shared something."""
from __future__ import annotations

from core.lang.i18n import tr

VERIFIED = "October 2026"

# (country, [(text, phone or "", link or "")]). The text is an English key that i18n translates.
SECTIONS = [
    ("Singapore", [
        ("Not sure? ScamShield helpline, open 24 hours:", "1799", ""),
        ("Report a scam online (ScamShield):", "", "https://go.gov.sg/scamreport"),
        ("Anti-Scam Helpline, for advice:", "1800-722-6688", ""),
    ]),
    ("Malaysia", [
        ("Lost money? National Scam Response Centre, call now:", "997", ""),
        ("The call counts as a police report, so you don't need to make another.", "", ""),
        ("Check a phone number, bank account or company (Semak Mule):", "", "https://semakmule.rmp.gov.my/"),
    ]),
]


def lines(lang: str) -> list[dict]:
    """[{country, items: [{text, tel, url, url_text}]}] in `lang`: what the website's help panel prints."""
    out = []
    for country, items in SECTIONS:
        out.append({"country": tr(country, lang), "items": [
            {"text": tr(t, lang), "tel": tel, "url": url, "url_text": url.split("://", 1)[-1].rstrip("/") if url else ""} for t, tel, url in items]})
    return out


def text(lang: str) -> str:
    """The same, as plain text for a chat message (Telegram makes the web addresses tappable by itself)."""
    parts = ["🆘 " + tr("Already paid or shared something? Call your bank straight away, then use an official line:", lang)]
    for c in lines(lang):
        block = [c["country"]]
        for it in c["items"]:
            tail = f" {it['tel']}" if it["tel"] else (f" {it['url_text']}" if it["url"] else "")
            block.append("• " + it["text"] + tail)
        parts.append("\n".join(block))
    parts.append(tr("Real officials never ask you to move money or share your bank login by phone.", lang))
    parts.append(tr("Official lines checked against government pages in {when}.", lang, when=tr(VERIFIED, lang)))
    return "\n\n".join(parts)


def short(lang: str) -> str:
    """One line for the end of a scam verdict in a chat."""
    return tr("🆘 Already paid or shared something? Singapore: call your bank, then 1799. Malaysia: call 997 now. More: /report", lang)
