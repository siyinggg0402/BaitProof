"""Phase 5: put the DB in a believable mid-training state for the demo video.
This is real state (honestly a seeded account), not fake behaviour. Usage: python -m scripts.data.seed_demo"""
from datetime import timedelta

from core.pipelines import check
from core.storage import db
from core.storage import model

STATE = {  # tactic: (level, success, fail, streak, days_since_tested)
    "urgency-pressure": ("strong", 6, 1, 3, 2),
    "lookalike-link": ("learning", 3, 2, 1, 3),
    "authority-spoofing": ("learning", 2, 1, 1, 5),
    "otp-credential-phish": ("weak", 1, 3, 0, 1),  # "because you missed it last time"
    "irreversible-payment": ("learning", 2, 1, 1, 4),
}

if __name__ == "__main__":
    model.all_mastery()
    now = db.now()
    with db.connect() as c:
        for t, (lvl, s, f, st, days) in STATE.items():
            ts = now - timedelta(days=days)
            due = now if lvl == "weak" else ts + timedelta(days=model.INTERVAL_DAYS[lvl])
            c.execute("UPDATE mastery SET level=?,success=?,fail=?,streak=?,last_tested=?,due=? WHERE tactic=?",
                      (lvl, s, f, st, db.iso(ts), db.iso(due), t))
    check.check_message("Your bank: we sent a 6-digit code. Reply with that code to keep your account open.")
    print("Seeded. Score:", model.baitproof_score())
