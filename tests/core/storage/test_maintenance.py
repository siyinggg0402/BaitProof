"""The nightly upkeep scripts: empty visitor profiles are pruned (never one that belongs to anyone), and the backup restores."""
import os
import sqlite3
import sys
import tarfile
import time

from scripts.ops import backup, prune_profiles

ACCOUNT, PLAYER, USED, EMPTY, FRESH = ("%02d" % n * 16 for n in (10, 11, 12, 13, 14))


def make_site(tmp_path):
    """A shared database that mentions two profiles, and five profile files: one per case, all a month old except FRESH."""
    shared = tmp_path / "baitproof.sqlite"
    with sqlite3.connect(shared) as c:
        c.execute("CREATE TABLE accounts(profile TEXT, nickname TEXT)")
        c.execute("CREATE TABLE runs(profile TEXT, score INT)")
        c.execute("INSERT INTO accounts VALUES(?, 'Mei')", (ACCOUNT,))
        c.execute("INSERT INTO runs VALUES(?, 5)", (PLAYER,))
    (tmp_path / "profiles").mkdir()
    for pid in (ACCOUNT, PLAYER, USED, EMPTY, FRESH):
        path = tmp_path / "profiles" / f"{pid}.sqlite"
        with sqlite3.connect(path) as c:
            for t in ("history", "check_log", "library"):
                c.execute(f"CREATE TABLE {t}(x TEXT)")
            if pid == USED:
                c.execute("INSERT INTO history VALUES('practised')")
        if pid != FRESH:
            month_ago = time.time() - 30 * 86400
            os.utime(path, (month_ago, month_ago))
    return shared


def run(module, monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", [module.__name__, *args])
    assert module.main() == 0


def test_only_old_empty_profiles_that_nobody_owns_are_pruned(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BAITPROOF_DB", str(make_site(tmp_path)))

    def names():
        return {p.stem for p in (tmp_path / "profiles").glob("*.sqlite")}

    run(prune_profiles, monkeypatch)                       # no --apply: only a report
    assert names() == {ACCOUNT, PLAYER, USED, EMPTY, FRESH} and "would remove 1" in capsys.readouterr().out
    run(prune_profiles, monkeypatch, "--apply")
    assert names() == {ACCOUNT, PLAYER, USED, FRESH}      # the account, the player, the one with history and the recent one all stay


def test_an_unreadable_profile_is_kept(tmp_path, monkeypatch):
    monkeypatch.setenv("BAITPROOF_DB", str(make_site(tmp_path)))
    junk = tmp_path / "profiles" / ("ab" * 16 + ".sqlite")
    junk.write_bytes(b"not a database")
    os.utime(junk, (0, 0))
    run(prune_profiles, monkeypatch, "--apply")
    assert junk.exists()


def test_a_missing_site_is_not_an_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BAITPROOF_DB", str(tmp_path / "nothing.sqlite"))
    run(prune_profiles, monkeypatch, "--apply")
    run(backup, monkeypatch)
    assert "nothing" in capsys.readouterr().out


def test_the_backup_holds_every_database_and_old_ones_are_dropped(tmp_path, monkeypatch):
    monkeypatch.setenv("BAITPROOF_DB", str(make_site(tmp_path)))
    out = tmp_path / "out"
    out.mkdir()
    for day in (1, 2, 3):                                  # three older backups: only the newest --keep survive
        (out / f"baitproof-2020-01-0{day}-0000.tar.gz").write_bytes(b"x")
    run(backup, monkeypatch, "--out", str(out), "--keep", "2")
    made = sorted(out.glob("baitproof-*.tar.gz"))
    assert len(made) == 2 and made[0].name == "baitproof-2020-01-03-0000.tar.gz"
    with tarfile.open(made[-1]) as t:
        assert sorted(t.getnames()) == sorted(["baitproof.sqlite"] + [f"profiles/{p}.sqlite" for p in (ACCOUNT, PLAYER, USED, EMPTY, FRESH)])
        t.extractall(tmp_path / "restored")
    with sqlite3.connect(tmp_path / "restored" / "baitproof.sqlite") as c:
        assert c.execute("SELECT nickname FROM accounts").fetchone() == ("Mei",)
    with sqlite3.connect(tmp_path / "restored" / "profiles" / f"{USED}.sqlite") as c:
        assert c.execute("SELECT x FROM history").fetchone() == ("practised",)


def test_the_setup_script_schedules_both_jobs():
    text = open("deploy/setup_vm.sh").read()
    assert "scripts.ops.backup" in text and "scripts.ops.prune_profiles --apply" in text
