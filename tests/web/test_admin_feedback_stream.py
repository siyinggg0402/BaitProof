import json
import re

import pytest
from fastapi.testclient import TestClient

from core.obs import logger
from web import deps, results
from web.main import app

SECRET = "zebra-unicorn-4242"
MSG = f"Buy 4 gift cards and send me the codes right now. Ref {SECRET}"


@pytest.fixture
def client():
    deps.HITS.clear()
    deps.LOGIN_HITS.clear()
    return TestClient(app)


@pytest.fixture
def admin_on(monkeypatch):
    monkeypatch.setenv("BAITPROOF_ADMIN_TOKEN", "s3cret-token")


# ---------------------------------------------------------------- admin
def test_admin_does_not_exist_unless_a_token_is_configured(client):
    for path in ("/admin", "/admin/login", "/admin/metrics.json"):
        assert client.get(path, follow_redirects=False).status_code == 404


def test_admin_requires_login_and_cookie_is_not_the_token(client, admin_on):
    assert client.get("/admin", follow_redirects=False).headers["location"] == "/admin/login"
    assert client.get("/admin/metrics.json").status_code == 401
    bad = client.post("/admin/login", data={"token": "nope"})
    assert bad.status_code == 401 and "That token" in bad.text
    ok = client.post("/admin/login", data={"token": "s3cret-token"}, follow_redirects=False)
    assert ok.status_code == 303 and "bp_admin" in ok.headers["set-cookie"] and "s3cret-token" not in ok.headers["set-cookie"]
    assert "httponly" in ok.headers["set-cookie"].lower() and "samesite=strict" in ok.headers["set-cookie"].lower()
    page = client.get("/admin")
    assert page.status_code == 200 and "Is it running OK?" in page.text and page.headers["cache-control"] == "no-store"
    assert client.post("/admin/logout", follow_redirects=False).status_code == 303


def test_admin_header_token_works_for_the_json_api(client, admin_on):
    assert client.get("/admin/metrics.json", headers={"x-admin-token": "wrong"}).status_code == 401
    r = client.get("/admin/metrics.json", headers={"x-admin-token": "s3cret-token"})
    assert r.status_code == 200 and set(r.json()) == {"health", "summary", "recent", "hours"}


def test_admin_login_is_rate_limited(client, admin_on):
    codes = [client.post("/admin/login", data={"token": "x"}).status_code for _ in range(10)]
    assert codes[:8] == [401] * 8 and codes[8] == 429


def test_dashboard_shows_numbers_but_never_message_text(client, admin_on):
    client.post("/check", data={"message": MSG})
    client.post("/check", data={"message": "Lunch on Sunday at ours? Everyone's coming around 1."})
    client.post("/admin/login", data={"token": "s3cret-token"})
    html = client.get("/admin?hours=24").text
    data = client.get("/admin/metrics.json").json()
    assert data["summary"]["checks"] == 2 and "scam" in data["summary"]["verdicts"] and len(data["recent"]) == 2
    for blob in (html, json.dumps(data), open(logger.path()).read()):
        assert SECRET not in blob and "gift cards" not in blob and "Lunch on Sunday" not in blob
    assert "Recent checks" in html and "Gates that tripped" in html and "Where the time goes" in html


def test_dashboard_turns_red_on_errors_and_names_the_problem(client, admin_on):
    logger.emit({"kind": "error", "where": "check", "type": "KeyError"})
    client.post("/admin/login", data={"token": "s3cret-token"})
    html = client.get("/admin").text
    assert "Something is broken" in html and "internal error" in html


def test_unknown_time_window_falls_back_to_24h(client, admin_on):
    client.post("/admin/login", data={"token": "s3cret-token"})
    assert client.get("/admin/metrics.json?hours=99999").json()["hours"] == 24


# ---------------------------------------------------------------- feedback
def test_feedback_is_logged_without_the_message_and_joined_to_the_verdict(client, admin_on):
    html = client.post("/check", data={"message": MSG}).text
    cid = re.search(r'data-check="([0-9a-f]{12})"', html).group(1)
    assert client.post("/api/feedback", json={"check_id": cid, "rating": "up"}).json() == {"ok": True}
    client.post("/api/feedback", json={"check_id": cid, "rating": "up"})  # same visitor, same check: counted once
    client.post("/admin/login", data={"token": "s3cret-token"})
    s = client.get("/admin/metrics.json").json()["summary"]
    assert s["feedback"] == {"up": 1, "down": 0} and s["feedback_by_verdict"] == {"scam": {"up": 1, "down": 0}}
    assert SECRET not in open(logger.path()).read()


@pytest.mark.parametrize("body", [{"check_id": "abc", "rating": "up"}, {"check_id": "0123456789ab", "rating": "meh"},
                                  {"check_id": "../../etc/pass", "rating": "up"}, {"check_id": "0123456789ab"}])
def test_feedback_rejects_garbage(client, body):
    assert client.post("/api/feedback", json=body).status_code == 422


def test_result_page_offers_feedback_buttons(client):
    html = client.post("/check", data={"message": MSG}).text
    assert 'data-feedback="up"' in html and 'data-feedback="down"' in html and "Was this right?" in html


# ---------------------------------------------------------------- live stream
def _stream(client, message):
    events = []
    with client.stream("POST", "/api/check/stream", json={"message": message}) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def test_stream_emits_each_gate_then_done(client):
    ev = _stream(client, MSG)
    stages = [e["data"]["stage"] for e in ev if e["type"] == "step"]
    assert stages[:2] == ["ingest", "intent"] and {"tools", "arbiter", "sufficiency", "output", "flywheel"} <= set(stages)
    assert ev[-1]["type"] == "done" and re.fullmatch(r"[0-9a-f]{12}", ev[-1]["data"])
    assert all(isinstance(e["data"]["ms"], int) for e in ev if e["type"] == "step")


def test_finished_result_is_fetchable_once_rendered_and_expires(client, monkeypatch):
    cid = _stream(client, MSG)[-1]["data"]
    r = client.get(f"/result/{cid}")
    assert r.status_code == 200 and "SCAM" in r.text and "The evidence" in r.text and "Investigated" not in r.text
    assert "Read the message" in r.text  # friendly stage names in 'How I decided'
    monkeypatch.setattr(results.time, "time", lambda: 10**12)
    assert client.get(f"/result/{cid}").status_code == 404
    assert client.get("/result/doesnotexist").status_code == 404


def test_stream_rejects_empty_message_and_is_rate_limited(client, monkeypatch):
    assert client.post("/api/check/stream", json={"message": "   "}).status_code == 400
    monkeypatch.setattr(deps, "RATE", 2)
    deps.HITS.clear()
    codes = [client.post("/api/check/stream", json={"message": "hello there"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_results_are_private_to_each_visitor(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    a, b = TestClient(app), TestClient(app)
    a.get("/")
    b.get("/")
    cid = _stream(a, MSG)[-1]["data"]
    assert a.get(f"/result/{cid}").status_code == 200
    assert b.get(f"/result/{cid}").status_code == 404  # a different visitor can't read someone else's result


def test_stream_internal_error_is_reported_not_hung(client, monkeypatch):
    from core.pipelines import check as check_pipeline
    monkeypatch.setattr(check_pipeline, "check_message", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    ev = _stream(client, "hello there")
    assert ev[-1] == {"type": "error", "data": "RuntimeError"}


def test_no_script_fallback_page_still_works_and_loads_the_live_script(client):
    html = client.get("/").text
    assert 'id="check-form"' in html and "/static/js/check.js" in html and 'id="live"' in html
    assert "SCAM" in client.post("/check", data={"message": MSG}).text  # plain form post still renders a result
