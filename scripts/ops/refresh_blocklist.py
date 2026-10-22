"""Download the public phishing-site list (Phishing.Database, MIT) to this machine, or show how fresh the copy is.
Usage: python -m scripts.ops.refresh_blocklist [--status]
The web app and the bot also refresh it by themselves once a day; this is for a first fill (so the very first check already has it) or a manual update."""
import sys

import core  # noqa: F401  loads .env
from core.pipelines.check import blocklist


def main() -> int:
    if "--status" in sys.argv:
        age = blocklist.age_seconds()
        print(f"{blocklist.db_path()}: " + ("not downloaded yet" if age is None else f"{blocklist.size():,} names, {age / 3600:.1f} hours old"))
        return 0
    try:
        n = blocklist.refresh(force=True)
    except Exception as e:  # the old copy, if any, is kept
        print(f"could not refresh the list: {type(e).__name__}: {e}")
        return 1
    print(f"{n:,} known phishing sites saved to {blocklist.db_path()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
