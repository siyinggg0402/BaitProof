"""The controlled tactic vocabulary (PLAN §3). Grow it deliberately, never per message."""
from __future__ import annotations

TACTICS: dict[str, dict[str, str]] = {
    "urgency-pressure": {
        "label": "Rushing you",
        "blurb": "They say you must act right now, so you don't stop to think.",
        "tell": "Real companies give you time. A deadline of hours is a pressure trick.",
        "action": "Stop. Don't reply or pay. Check by calling a number you already trust.",
    },
    "authority-spoofing": {
        "label": "Pretending to be the boss",
        "blurb": "They claim to be police, a bank or a company to make you obey.",
        "tell": "Real officials don't tell you to keep it secret or to move your money.",
        "action": "Hang up or ignore it. Call the real office using a number you look up yourself.",
    },
    "otp-credential-phish": {
        "label": "Asking for your code or password",
        "blurb": "They want a code, PIN or password sent to your phone.",
        "tell": "Nobody real ever needs the code that was sent to you. It is the key to your account.",
        "action": "Never share the code. Sign in on the official app or website yourself.",
    },
    "irreversible-payment": {
        "label": "Gift cards, crypto or wire money",
        "blurb": "They ask for payment that can't be taken back.",
        "tell": "Gift cards, crypto and wire transfers are how scammers get paid. Real bills never use them.",
        "action": "Do not pay. Money sent this way is almost never returned.",
    },
    "lookalike-link": {
        "label": "Fake website address",
        "blurb": "The link looks like a real company but the address is slightly off.",
        "tell": "Read the web address slowly. A real company's address ends with its own name, like amazon.com. Extra words or strange endings mean fake.",
        "action": "Don't tap the link. Open the company's real website or app by typing it yourself.",
    },
    "too-good-to-be-true": {
        "label": "Too good to be true",
        "blurb": "A prize, huge profit or easy money with no catch.",
        "tell": "If you didn't enter and it sounds amazing, it's bait.",
        "action": "Ignore it. You can't win a contest you never entered.",
    },
    "emotional-manipulation": {
        "label": "Playing on your feelings",
        "blurb": "A loved one in trouble, romance, or threats to scare you.",
        "tell": "They use fear or love so you act before you think. They also say not to call.",
        "action": "Pause. Call the person on the number you already have. Ask a question only they would know.",
    },
    "remote-access-request": {
        "label": "Asking to control your computer",
        "blurb": "They want you to install an app so they can 'fix' something.",
        "tell": "Real support never contacts you first and asks you to install remote-control apps.",
        "action": "Do not install anything. Hang up. If you did, turn off the internet and call your bank.",
    },
    "advance-fee": {
        "label": "Pay a fee first",
        "blurb": "To get money, a loan or a prize, you must pay a small fee first.",
        "tell": "Real prizes and loans never ask you to pay before you receive them.",
        "action": "Do not pay the fee. There is no money waiting for you.",
    },
    "impersonation-official": {
        "label": "Pretending to be an office or company",
        "blurb": "A message dressed up as the tax office, health service, courier or a bank.",
        "tell": "Official offices write letters and don't text you to pay or 'confirm' details by link.",
        "action": "Ignore it. Contact the office through its official website or the number on your card.",
    },
    "investment-crypto": {
        "label": "Fake investment",
        "blurb": "A 'sure thing' investment with big returns, often in crypto.",
        "tell": "Promised high returns and pressure to deposit are the signs of a fake investment.",
        "action": "Don't deposit money. Talk to someone you trust before you invest anything.",
    },
    "job-task-scam": {
        "label": "Fake job or tasks",
        "blurb": "Easy online work where you must deposit money to 'unlock' pay.",
        "tell": "A real job pays you. It never asks you to pay in or top up a balance.",
        "action": "Walk away. Don't deposit anything for a job.",
    },
}

def valid(tid: str) -> bool:
    return tid in TACTICS


def label(tid: str) -> str:
    return TACTICS[tid]["label"]


def vocabulary_prompt() -> str:
    return "\n".join(f"- {k}: {v['blurb']}" for k, v in TACTICS.items())
