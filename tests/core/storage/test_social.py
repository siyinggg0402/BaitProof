"""Accounts, friends and the friends' leaderboard: no emails or passwords, a key kept only as a hash, mutual friends by code, rows seen only by friends."""
import pytest

from core.storage import accounts, db, runs
from core.storage.accounts import AccountError

ME, MEI, RAJ = "a" * 32, "b" * 32, "c" * 32


def make(profile, name, avatar=""):
    return accounts.create(profile, name, avatar)


def test_a_profile_becomes_an_account_with_a_key_shown_once():
    acct, key = make(ME, "  Aiman   Z ", "🦊")
    assert acct["nickname"] == "Aiman Z" and acct["avatar"] == "🦊" and len(acct["friend_code"]) == 6
    assert len(key) == 19 and key.count("-") == 3
    with db.connect(shared=True) as c:  # the key is not stored, only its hash
        stored = " ".join(str(v) for r in c.execute("SELECT * FROM accounts").fetchall() for v in tuple(r))
    assert key not in stored and key.replace("-", "") not in stored
    assert accounts.get(ME)["nickname"] == "Aiman Z" and accounts.get("f" * 32) is None
    with pytest.raises(AccountError):
        make(ME, "Again")


@pytest.mark.parametrize("bad", ["", "a", "x" * 17, "evil.com", "see http://x.top", "a/b", "@admin", "<b>hi</b>"])
def test_nicknames_are_short_and_can_never_be_a_web_address(bad):
    with pytest.raises(AccountError):
        make(ME, bad)


def test_stray_white_space_in_a_nickname_is_tidied():
    assert make(ME, "name\n\tline")[0]["nickname"] == "name line"


@pytest.mark.parametrize("ok", ["Mei", "小美", "Nur Aisyah", "Raj_2", "ah-boy", "Émile"])
def test_nicknames_in_any_script_are_fine(ok):
    assert make(ME, ok)[0]["nickname"] == ok


def test_a_bad_avatar_is_replaced_with_a_real_one():
    assert make(ME, "Mei", "<script>")[0]["avatar"] in accounts.AVATARS


def test_signing_in_needs_the_key_and_tolerates_how_it_is_typed():
    _, key = make(ME, "Mei")
    assert accounts.sign_in(key) == ME
    assert accounts.sign_in(key.lower().replace("-", " ")) == ME and accounts.sign_in("  " + key + "  ") == ME
    assert accounts.sign_in("AAAA-BBBB-CCCC-DDDD") is None and accounts.sign_in("") is None and accounts.sign_in("short") is None
    assert accounts.sign_in("0000-0000-0000-0000") is None  # (characters that are not in the alphabet)


def test_a_new_key_replaces_the_old_one_and_signing_in_is_rate_limited(monkeypatch):
    _, old = make(ME, "Mei")
    fresh = accounts.new_key(ME)
    assert accounts.sign_in(old) is None and accounts.sign_in(fresh) == ME
    monkeypatch.setattr(accounts, "GLOBAL_TRIES_PER_MINUTE", 3)
    accounts._TRIES.clear()
    for _ in range(3):
        accounts.sign_in("AAAA-BBBB-CCCC-DDDD")
    assert accounts.sign_in(fresh) is None  # a flood of guesses locks everyone out for a minute rather than let one through
    accounts._TRIES.clear()


def test_changing_the_name_and_the_avatar():
    make(ME, "Mei", "🐟")
    assert accounts.update(ME, nickname="Mei Ling", avatar="🐼")["nickname"] == "Mei Ling"
    assert accounts.update(ME, avatar="not-an-avatar")["avatar"] == "🐼"
    with pytest.raises(AccountError):
        accounts.update(ME, nickname="x")
    with pytest.raises(AccountError):
        accounts.update(MEI, nickname="Nobody")


def test_friends_are_added_by_code_and_it_is_mutual():
    mei, _ = make(MEI, "Mei")
    make(ME, "Aiman")
    friend = accounts.add_friend(ME, mei["friend_code"].lower())
    assert friend["pub"] == mei["pub"] and set(friend) == {"pub", "nickname", "avatar"}
    assert [f["nickname"] for f in accounts.friends(ME)] == ["Mei"] and [f["nickname"] for f in accounts.friends(MEI)] == ["Aiman"]
    with pytest.raises(AccountError, match="already friends"):
        accounts.add_friend(ME, mei["friend_code"])
    with pytest.raises(AccountError, match="already friends"):
        accounts.add_friend(MEI, accounts.get(ME)["friend_code"])


def test_friend_codes_cannot_be_abused():
    me, _ = make(ME, "Aiman")
    with pytest.raises(AccountError, match="own code"):
        accounts.add_friend(ME, me["friend_code"])
    for bad in ("", "ZZZZZZ", "12", "AAAAAAAAAA"):
        with pytest.raises(AccountError, match="doesn't match"):
            accounts.add_friend(ME, bad)
    with pytest.raises(AccountError, match="Create your profile"):
        accounts.add_friend(RAJ, me["friend_code"])


def test_a_new_code_stops_the_old_one_but_keeps_existing_friends():
    mei, _ = make(MEI, "Mei")
    make(ME, "Aiman")
    accounts.add_friend(ME, mei["friend_code"])
    fresh = accounts.new_friend_code(MEI)
    make(RAJ, "Raj")
    with pytest.raises(AccountError):
        accounts.add_friend(RAJ, mei["friend_code"])
    assert accounts.add_friend(RAJ, fresh)["pub"] == mei["pub"]
    assert len(accounts.friends(ME)) == 1


def test_either_side_can_end_a_friendship_and_deleting_an_account_removes_everything():
    mei, _ = make(MEI, "Mei")
    make(ME, "Aiman")
    accounts.add_friend(ME, mei["friend_code"])
    assert accounts.remove_friend(MEI, accounts.get(ME)["pub"]) and not accounts.remove_friend(MEI, accounts.get(ME)["pub"]) and not accounts.remove_friend(MEI, "nobody")
    assert accounts.friends(ME) == [] and accounts.friends(MEI) == []
    accounts.add_friend(ME, mei["friend_code"])
    runs.record(ME, runs.ROAD, 400)
    accounts.delete(ME)
    assert accounts.get(ME) is None and accounts.friends(MEI) == [] and runs.best(ME) == 0


def test_friend_lists_are_capped(monkeypatch):
    monkeypatch.setattr(accounts, "MAX_FRIENDS", 2)
    me, _ = make(ME, "Aiman")
    for i, pid in enumerate(("1" * 32, "2" * 32, "3" * 32)):
        make(pid, f"Friend{i}")
    accounts.add_friend("1" * 32, me["friend_code"])
    accounts.add_friend("2" * 32, me["friend_code"])
    with pytest.raises(AccountError, match="full"):
        accounts.add_friend("3" * 32, me["friend_code"])


def test_the_leaderboard_ranks_you_and_your_friends_and_nobody_else():
    mei, _ = make(MEI, "Mei")
    make(ME, "Aiman")
    make(RAJ, "Raj")                                  # a stranger: never on the board
    accounts.add_friend(ME, mei["friend_code"])
    runs.record(MEI, runs.ROAD, 640, 8)
    runs.record(MEI, runs.ROAD, 240, 3)
    runs.record(ME, runs.ROAD, 400, 5)
    runs.record(RAJ, runs.ROAD, 9999, 99)
    rows = runs.board(ME)
    assert [(r["nickname"], r["best"], r["rank"], r["you"]) for r in rows] == [("Mei", 640, 1, False), ("Aiman", 400, 2, True)]
    assert rows[0]["runs"] == 2
    assert [g["nickname"] for g in runs.ghosts(ME)] == ["Mei"] and runs.ghosts(ME)[0]["best"] == 640


def test_friends_without_a_run_come_last_and_are_unranked():
    mei, _ = make(MEI, "Mei")
    make(ME, "Aiman")
    accounts.add_friend(ME, mei["friend_code"])
    runs.record(ME, runs.ROAD, 0)
    rows = runs.board(ME)
    assert [(r["nickname"], r["rank"]) for r in rows] == [("Aiman", 1), ("Mei", 0)]


def test_this_week_and_all_time_differ(monkeypatch):
    make(ME, "Aiman")
    with db.connect(shared=True) as c:
        c.execute("INSERT INTO runs(profile,game,score,correct,ts) VALUES(?,?,?,?,?)", (ME, runs.ROAD, 900, 11, "2020-01-01T00:00:00+00:00"))
    runs.record(ME, runs.ROAD, 120)
    assert runs.board(ME, "week")[0]["best"] == 120 and runs.board(ME, "all")[0]["best"] == 900
    assert runs.best(ME, since=runs.week_start()) == 120


def test_a_profile_id_is_a_session_cookie_so_nothing_other_people_can_see_contains_one():
    mei, _ = make(MEI, "Mei")
    make(ME, "Aiman")
    accounts.add_friend(ME, mei["friend_code"])
    runs.record(MEI, runs.ROAD, 500, 6)
    seen = repr([accounts.friends(ME), accounts.invite_card(mei["friend_code"]), runs.board(ME, "week"), runs.board(ME, "all"), runs.ghosts(ME)])
    assert MEI not in seen and ME not in seen and mei["friend_code"] not in seen
    assert set(accounts.invite_card(mei["friend_code"])) == {"pub", "nickname", "avatar"} and accounts.invite_card("nope") is None
    assert accounts.get(MEI)["pub"] != MEI and len(accounts.get(MEI)["pub"]) == 12
