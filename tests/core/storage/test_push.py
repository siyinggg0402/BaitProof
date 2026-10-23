"""Web Push: opt-in per browser, only for people with a profile, only to browsers' own push services, rate limited, in the friend's language, and off without keys."""
import base64
import json

import pytest

from core.game import road
from core.game import pool as gp
from core.storage import accounts, push, runs

ME, MEI = "a" * 32, "b" * 32
EP = "https://fcm.googleapis.com/fcm/send/abc123"
KEY, AUTH = "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM", "tBHItJI5svbpez7KI4CCXg"


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    from py_vapid import Vapid
    from cryptography.hazmat.primitives import serialization

    v = Vapid()
    v.generate_keys()
    b64 = lambda raw: base64.urlsafe_b64encode(raw).rstrip(b"=").decode()  # noqa: E731
    monkeypatch.setenv("VAPID_PRIVATE_KEY", b64(v.private_key.private_numbers().private_value.to_bytes(32, "big")))
    monkeypatch.setenv("VAPID_PUBLIC_KEY", b64(v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)))
    monkeypatch.setenv("VAPID_SUBJECT", "mailto:ops@example.com")
    monkeypatch.setattr(push, "SYNC", True)
    push._sent.clear()
    accounts.create(ME, "Aiman")
    accounts.create(MEI, "Mei")


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(push, "_send", lambda sub, payload: out.append((sub, payload)) or True)
    return out


def test_it_is_off_until_both_keys_are_set(monkeypatch):
    assert push.enabled() and push.public_key()
    monkeypatch.delenv("VAPID_PRIVATE_KEY")
    assert not push.enabled() and push.public_key() == "" and push.notify_passed(ME, [(MEI, 100)], 500, "road") == 0


def test_a_browser_subscribes_only_with_a_profile_and_a_real_push_service():
    with pytest.raises(push.PushError, match="Make a profile"):
        push.subscribe("c" * 32, EP, KEY, AUTH)
    for bad in ("http://fcm.googleapis.com/x", "https://evil.example.com/x", "https://fcm.googleapis.com.evil.com/x", "https://localhost/x", "https://127.0.0.1/x",
                "https://user:pw@fcm.googleapis.com/x", "https://fcm.googleapis.com/" + "a" * 1300, "javascript:alert(1)", ""):
        with pytest.raises(push.PushError, match="doesn't look like"):
            push.subscribe(ME, bad, KEY, AUTH)
    with pytest.raises(push.PushError):
        push.subscribe(ME, EP, "short", AUTH)
    for ok in (EP, "https://updates.push.services.mozilla.com/wpush/v2/xyz", "https://wns2-par02p.notify.windows.com/w/?token=abc", "https://web.push.apple.com/QGx"):
        push.subscribe(ME, ok, KEY, AUTH)
    assert push.count(ME) == 4


def test_a_profile_can_have_five_devices_and_resubscribing_the_same_one_is_fine():
    for i in range(5):
        push.subscribe(ME, f"{EP}{i}", KEY, AUTH)
    with pytest.raises(push.PushError, match="five devices"):
        push.subscribe(ME, EP + "x", KEY, AUTH)
    push.subscribe(ME, EP + "0", KEY, AUTH, "ms")
    assert push.count(ME) == 5 and push.unsubscribe(ME, EP + "0") and not push.unsubscribe(ME, EP + "0") and push.count(ME) == 4


def test_deleting_the_profile_forgets_its_devices():
    push.subscribe(ME, EP, KEY, AUTH)
    accounts.delete(ME)
    assert push.count(ME) == 0


def test_a_friend_who_asked_is_told_in_their_own_language_and_nobody_else_is(sent):
    push.subscribe(MEI, EP, KEY, AUTH, "ms")
    assert push.notify_passed(ME, [(MEI, 400)], 640, "road") == 1
    (sub, payload), = sent
    assert sub["endpoint"] == EP and payload["title"] == "🏁 Aiman baru sahaja melepasi rekod terbaik anda!" and "640 m" in payload["body"] and "400 m" in payload["body"]
    assert payload["url"] == "/road" and ME not in json.dumps(payload) and MEI not in json.dumps(payload) and "a" * 32 not in json.dumps(payload)
    sent.clear()
    assert push.notify_passed(ME, [(ME, 1)], 640, "road") == 0 and sent == []      # (never the person who just drove)
    assert push.notify_passed(MEI, [(ME, 1)], 640, "road") == 0                    # (Aiman has no devices)


def test_the_daily_road_notification_opens_the_daily_road_and_english_is_the_default(sent):
    push.subscribe(MEI, EP, KEY, AUTH)
    push.notify_passed(ME, [(MEI, 240)], 480, "daily")
    payload = sent[0][1]
    assert payload["title"] == "🏁 Aiman just passed your best!" and "today's Daily Road" in payload["body"] and payload["url"] == "/road?daily=1"


def test_nobody_is_nudged_more_than_three_times_an_hour(sent):
    push.subscribe(MEI, EP, KEY, AUTH)
    assert [push.notify_passed(ME, [(MEI, 1)], 100 * (i + 1), "road") for i in range(5)] == [1, 1, 1, 0, 0]


def test_a_gone_browser_is_removed_and_other_failures_leave_it(monkeypatch):
    from pywebpush import WebPushException

    class Resp:
        def __init__(self, code):
            self.status_code = code

    def fail(code):
        def boom(**_):
            raise WebPushException("gone", response=Resp(code))
        return boom

    push.subscribe(MEI, EP, KEY, AUTH)
    monkeypatch.setattr("pywebpush.webpush", fail(500))
    sub = push._subs(MEI)[0]
    assert push._send(sub, {"title": "x"}) is False and push.count(MEI) == 1
    monkeypatch.setattr("pywebpush.webpush", fail(410))
    assert push._send(sub, {"title": "x"}) is False and push.count(MEI) == 0


def test_the_real_sender_signs_with_the_sites_key_and_sends_a_small_json_message(monkeypatch):
    calls = []
    monkeypatch.setattr("pywebpush.webpush", lambda **kw: calls.append(kw))
    push.subscribe(MEI, EP, KEY, AUTH)
    assert push._send(push._subs(MEI)[0], {"title": "T", "body": "B"}) is True
    kw = calls[0]
    assert kw["subscription_info"] == {"endpoint": EP, "keys": {"p256dh": KEY, "auth": AUTH}} and json.loads(kw["data"]) == {"title": "T", "body": "B"}
    assert kw["vapid_claims"] == {"sub": "mailto:ops@example.com"} and kw["ttl"] == 3600 and kw["timeout"] == 8


def test_finishing_a_drive_that_passes_a_friend_notifies_that_friend(sent):
    mei, _ = accounts.create("c" * 32, "Raj")
    accounts.add_friend(ME, mei["friend_code"])
    accounts.add_friend(ME, accounts.get(MEI)["friend_code"])
    runs.record(MEI, runs.ROAD, 160, 2)
    runs.record("c" * 32, runs.ROAD, 900, 11)       # Raj is far ahead: not passed
    push.subscribe(MEI, EP, KEY, AUTH)
    push.subscribe("c" * 32, EP + "r", KEY, AUTH)
    pool = [gp.Item(f"s{i}", f"Scam {i}", "scam", ["urgency-pressure"], "t", "scam", "a", "seed") for i in range(8)] + [gp.Item(f"f{i}", f"Fine {i}", "safe", [], "t", "", "a", "seed") for i in range(4)]
    out = road.start(ME, pool=pool)
    r = road.get(out["run"], ME)
    for _ in range(4):   # 320 m
        gid, item = next((g, i) for g, i in r.gates if g not in r.answered)
        road.answer(r, gid, 0 if item.truth == "scam" else 2)
    road.finish(r)
    assert [s["endpoint"] for s, _ in sent] == [EP] and "320 m" in sent[0][1]["body"] and "160 m" in sent[0][1]["body"]
