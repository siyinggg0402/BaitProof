"""Things that went wrong on a real server once, kept from happening again."""
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]


def test_the_services_do_not_use_environmentfile():
    """systemd keeps a trailing `# comment` as part of the value (BAITPROOF_RATE=30  # ... crashed the site on start) and lets .env override the paths the unit sets.
    The app reads .env itself with python-dotenv."""
    for name in ("baitproof.service", "baitproof-bot.service"):
        lines = (ROOT / "deploy" / name).read_text().splitlines()
        assert not [ln for ln in lines if ln.startswith("EnvironmentFile")], name


def test_every_number_in_the_example_env_reads_as_a_number():
    for key, value in dotenv_values(ROOT / ".env.example").items():
        if value and key.startswith("BAITPROOF_") and key.split("_")[-1] in ("RATE", "ROUNDS", "CALLS", "SECONDS", "TOKENS", "CONCURRENCY"):
            assert value.isdigit(), key


def test_the_setup_script_can_be_rerun_by_an_ordinary_user():
    text = (ROOT / "deploy" / "setup_vm.sh").read_text()
    assert 'chown -R "$USER"' not in text                  # the checkout belongs to the service user, so nothing is made as the person running the script
    assert "sudo grep -q '^TELEGRAM_BOT_TOKEN" in text     # and .env is locked to that user, so reading it needs sudo
    assert "sudo -u baitproof git" in text
