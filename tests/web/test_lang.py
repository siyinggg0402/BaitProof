"""The website in Chinese (Simplified and Traditional) as well as English: choosing a language, every page, every script string, the share card."""
import ast
import json
import re
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.lang import i18n
from core.domain.tactics import TACTICS
from web import cardimg, deps, ui
from web.main import app

ROOT = Path(__file__).resolve().parents[2]
CJK = re.compile(r"[一-鿿]")
SCAM_ZH = "【顺丰速运】您的快递因地址不详无法派送，请于24小时内点击 http://sf-express-cn.top/addr 补全信息并支付3元费用，逾期将退回。"
SCAM_EN = "Pay with gift cards today or you will be arrested. IRS notice."
SAME_IN_CHINESE = {"WhatsApp", "+{n} XP", "+50 XP", "{a} / {b} XP"}  # a brand and numbers: written the same in every language
SIMPLIFIED_ONLY = re.compile("[骗这个们来说对错还没关发开练习记录]")
# English wording of the interface that must never show on a Chinese page
LEFTOVER = ["Check it", "Check a message", "Practice", "Practise", "Train", "Games", "Records", "My records", "Delete", "Read aloud", "The giveaway", "What to do", "The evidence",
            "Red flag", "Reassuring", "Tricks found", "Challenge family", "Start practice", "Paste the message", "Your scam resilience", "Needs work", "Getting there",
            "Loading your game", "Quick practice", "Can you spot", "Take the challenge", "Family challenge", "Connect Telegram", "Not connected", "Website",
            "How I decided", "Was this right", "Your data", "Larger text", "Offline mode", "Private by design", "Example only", "Try an example"]


@pytest.fixture
def client():
    deps.HITS.clear()
    return TestClient(app)


def lang_client(code):
    deps.HITS.clear()
    c = TestClient(app)
    c.cookies.set("lang", code)
    return c


def visible(html: str) -> str:
    """The page without its <script> blocks (the translation dictionary is full of English keys on purpose) and without the language names."""
    html = re.sub(r"<script.*?</script>", "", html, flags=re.S)
    return re.sub(r'<details class="lang".*?</details>', "", html, flags=re.S)


def html_lang(html: str) -> str:
    return re.search(r'<html lang="([^"]+)"', html).group(1)


def new_challenge(c):
    return c.post("/challenge/new", follow_redirects=False).headers["location"].split("/")[-1]


# ------------------------------------------------------------------------------------------------ choosing the language
def test_english_is_the_default_and_the_page_declares_its_language(client):
    html = client.get("/").text
    assert html_lang(html) == "en" and 'id="i18n"' not in html and "Paste the message here" in html


def test_the_lang_cookie_chooses_the_language():
    for code, tag in (("en", "en"), ("zh", "zh-Hans"), ("zh-Hant", "zh-Hant")):
        assert html_lang(lang_client(code).get("/").text) == tag


def test_accept_language_is_used_when_there_is_no_cookie(client):
    assert html_lang(client.get("/", headers={"accept-language": "zh-TW,zh;q=0.9,en;q=0.8"}).text) == "zh-Hant"
    assert html_lang(client.get("/", headers={"accept-language": "zh-CN,zh;q=0.9"}).text) == "zh-Hans"
    assert html_lang(client.get("/", headers={"accept-language": "fr-FR,fr;q=0.9"}).text) == "en"
    assert html_lang(client.get("/", headers={"accept-language": "en-US,en;q=0.9,zh;q=0.5"}).text) == "en"


def test_the_cookie_beats_the_browser_and_a_bad_cookie_is_ignored():
    c = lang_client("en")
    assert html_lang(c.get("/", headers={"accept-language": "zh-CN"}).text) == "en"
    c = lang_client("klingon")
    assert html_lang(c.get("/", headers={"accept-language": "zh-CN"}).text) == "zh-Hans"


def test_switching_language_sets_a_year_long_cookie_and_goes_back(client):
    r = client.get("/lang/zh?next=/records", follow_redirects=False)
    assert r.status_code in (302, 303) and r.headers["location"] == "/records"
    cookie = r.headers["set-cookie"]
    assert "lang=zh" in cookie and "Max-Age=31536000" in cookie and "Path=/" in cookie and "SameSite=lax" in cookie
    assert html_lang(client.get("/records").text) == "zh-Hans"  # the cookie sticks
    assert client.get("/lang/zh-Hant", follow_redirects=False).headers["set-cookie"].startswith("lang=zh-Hant")
    assert client.get("/lang/ZH-hant", follow_redirects=False).headers["set-cookie"].startswith("lang=zh-Hant")
    assert client.get("/lang/en?next=/records?channel=web", follow_redirects=False).headers["location"] == "/records?channel=web"
    assert client.get("/lang/zh", follow_redirects=False).headers["location"] == "/"


@pytest.mark.parametrize("bad", ["//evil.com", "https://evil.com", "http://evil.com/x", "/\\evil.com", "javascript:alert(1)", "evil.com", "///evil.com", "/ok\r\nSet-Cookie: x=1", ""])
def test_the_language_switch_never_redirects_to_another_site(client, bad):
    r = client.get("/lang/zh", params={"next": bad}, follow_redirects=False)
    assert r.headers["location"] == "/"


def test_an_unknown_language_is_refused(client):
    assert client.get("/lang/klingon", follow_redirects=False).status_code == 404
    assert "set-cookie" not in client.get("/lang/xx", follow_redirects=False).headers


def test_html_varies_by_language(client):
    assert "Cookie" in client.get("/").headers["vary"] and "Accept-Language" in client.get("/").headers["vary"]


def test_the_switcher_lists_all_three_languages_and_returns_to_the_same_page():
    html = lang_client("zh").get("/records?channel=web").text
    assert 'class="lang"' in html and 'aria-current="true"' in html
    for code, name in (("en", "English"), ("zh", "简体中文"), ("zh-Hant", "繁體中文")):
        assert f'/lang/{code}?next=/records%3Fchannel%3Dweb' in html and name in html
    assert 'lang="zh-Hans"' in html and 'lang="zh-Hant"' in html  # each name is marked up in its own language


def test_the_switcher_on_the_result_of_a_post_returns_to_the_home_page(client):
    """A check is answered at /check, which only accepts POST: switching language there must not send the visitor back to it."""
    assert '/lang/zh?next=/"' in client.post("/check", data={"message": "hello there friend"}).text


# ------------------------------------------------------------------------------------------------ the pages
def test_english_pages_have_no_chinese_chrome(client):
    cid = new_challenge(client)
    for url in ("/", "/train", "/game", "/records", f"/challenge/{cid}", f"/card/{cid}?s=3"):
        html = client.get(url).text
        assert html_lang(html) == "en", url
        assert not CJK.search(visible(html)), (url, CJK.findall(visible(html))[:5])
    assert "Paste the message here" in client.get("/").text and "Start practice" in client.get("/train").text


def test_simplified_pages_are_in_chinese():
    c = lang_client("zh")
    cid = new_challenge(c)
    want = {"/": ["把消息贴在这里", "帮我检查", "更难被骗", "挑战家人", "查一查"], "/train": ["练习", "快速练习", "开始练习", "游戏", "收件箱快答", "你的防骗能力"], "/game": ["正在载入你的游戏"],
            "/records": ["我的记录", "删除我的全部记录", "连接 Telegram"], f"/challenge/{cid}": ["你能识破骗局吗？", "开始挑战"], f"/card/{cid}?s=3": ["接受挑战", "更多分享方式"]}
    for url, phrases in want.items():
        html = c.get(url).text
        assert html_lang(html) == "zh-Hans", url
        for p in phrases:
            assert p in html, (url, p)


def test_traditional_pages_use_traditional_characters():
    c = lang_client("zh-Hant")
    cid = new_challenge(c)
    for url in ("/", "/train", "/game", "/records", f"/challenge/{cid}", f"/card/{cid}?s=3"):
        html = c.get(url).text
        text = visible(html)
        assert html_lang(html) == "zh-Hant", url
        assert not SIMPLIFIED_ONLY.search(text), (url, SIMPLIFIED_ONLY.findall(text)[:5])
    assert "騙" in c.get("/").text and "骗" not in c.get("/").text and "更難被騙" in c.get("/").text
    assert "練習" in c.get("/train").text and "遊戲" in c.get("/train").text and "我的記錄" in c.get("/records").text


def test_titles_and_share_tags_follow_the_language():
    c = lang_client("zh")
    assert "<title>我的记录 · Baitproof</title>" in c.get("/records").text
    assert "<title>练习 · Baitproof</title>" in c.get("/train").text
    cid = new_challenge(c)
    page = c.get(f"/card/{cid}?s=3").text
    assert '<meta property="og:title" content="我的防骗力 50%">' in page and "3条" in page and "<title>我的防骗力 50%</title>" in page
    en = lang_client("en").get(f"/card/{cid}?s=3").text
    assert '<meta property="og:title" content="I&#39;m 50% Baitproof">' in en and "<title>I&#39;m 50% Baitproof</title>" in en


def test_a_link_preview_follows_the_language_of_the_link_not_the_crawlers():
    """Whoever shares in Chinese gets a Chinese preview: the link carries the language (a crawler has no cookie)."""
    c = lang_client("zh")
    cid = new_challenge(c)
    sub = c.post(f"/api/challenge/{cid}/submit", json={"answers": [True] * 6}).json()
    assert sub["card_url"].endswith("&lang=zh") and f"/card/{cid}?s=" in sub["card_url"]
    crawler = TestClient(app).get(sub["card_url"]).text
    assert "我的防骗力" in crawler and f"/card-image/{cid}.png?s={sub['right']}&amp;lang=zh" in crawler
    assert html_lang(crawler) == "en"  # the page itself stays in the visitor's own language
    en = lang_client("en")
    english = en.post(f"/api/challenge/{new_challenge(en)}/submit", json={"answers": [True] * 6}).json()
    assert "lang=" not in english["card_url"]  # English links are unchanged


def test_no_chinese_page_has_leftover_english_interface_text():
    c = lang_client("zh")
    c.post("/check", data={"message": SCAM_ZH})
    cid = new_challenge(c)
    pages = {"/": c.get("/").text, "/train": c.get("/train").text, "/game": c.get("/game").text, "/records": c.get("/records").text,
             "/challenge": c.get(f"/challenge/{cid}").text, "/card": c.get(f"/card/{cid}?s=3").text, "/check": c.post("/check", data={"message": SCAM_ZH}).text,
             "/check-en": c.post("/check", data={"message": SCAM_EN}).text}
    for name, html in pages.items():
        text = visible(html)
        for phrase in LEFTOVER:
            assert phrase not in text, (name, phrase)


def test_the_admin_pages_stay_in_english(monkeypatch):
    monkeypatch.setenv("BAITPROOF_ADMIN_TOKEN", "t0ken")
    html = lang_client("zh").get("/admin/login").text
    assert html_lang(html) == "en" and "Operator login" in html and not CJK.search(visible(html))


# ------------------------------------------------------------------------------------------------ the script dictionary
def i18n_block(html):
    m = re.search(r'<script type="application/json" id="i18n">(.*?)</script>', html, flags=re.S)
    return json.loads(m.group(1)) if m else None


def test_the_script_dictionary_is_only_on_chinese_pages():
    assert i18n_block(lang_client("en").get("/").text) is None
    zh = i18n_block(lang_client("zh").get("/").text)
    assert zh["lang"] == "zh" and zh["speech"] == "zh-CN" and zh["dict"]["Read aloud"] == "朗读" and zh["dict"]["Rushing you"] == "催你马上行动"
    hant = i18n_block(lang_client("zh-Hant").get("/game").text)
    assert hant["lang"] == "zh-Hant" and hant["speech"] == "zh-TW" and hant["dict"]["Try again"] == "再試一次" and "骗" not in json.dumps(hant, ensure_ascii=False)


def test_the_dictionary_cannot_break_out_of_its_script_tag():
    assert "<" not in ui.i18n_json("zh") and ">" not in ui.i18n_json("zh") and "</script" not in ui.i18n_json("zh-Hant")
    assert "\\u003c" in ui._safe_json({"x": "</script><!--"}) and " " not in ui._safe_json({"x": "a b"})


def test_every_string_the_scripts_translate_has_a_chinese_version():
    keys = ui.js_keys()
    assert len(keys) > 100 and "Read aloud" in keys and "Next →" in keys
    english_labels = {v["label"] for v in TACTICS.values()}  # the page adds the trick names itself
    missing = [k for k in keys if i18n.tr(k, "zh") == k and k not in english_labels and k not in SAME_IN_CHINESE]
    assert not missing, missing


def test_scripts_only_call_t_with_literal_text():
    """The dictionary is built by reading `t("...")` calls: a call with a variable, a joined string or a `${}` template would silently go untranslated."""
    for f in sorted((ROOT / "web/static/js").glob("*.js")):
        src = f.read_text()
        for m in re.finditer(r"(?<![\w.$])t\(\s*([^\s\"`])", src):
            assert src[:m.start()].endswith("function "), (f.name, src[m.start(): m.start() + 40])  # only the definition of t() itself
        assert not re.search(r"(?<![\w.$])t\(\s*(?:\"[^\"]*\"|`[^`]*`)\s*\+", src), f.name
        assert not re.search(r"(?<![\w.$])t\(\s*`[^`]*\$\{", src), f.name


def template_keys() -> dict[str, str]:
    keys = {}
    for f in sorted((ROOT / "web/templates").glob("*.html")):
        if f.name.startswith("admin"):
            continue
        s = f.read_text()
        for m in re.finditer(r"""\b(?:_|_h)\(\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')""", s):
            keys[ast.literal_eval(m.group(1))] = f.name
        for m in re.finditer(r"""tr_in\(\s*[\w.]+\s*,\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')""", s):
            keys[ast.literal_eval(m.group(1))] = f.name
        for m in re.finditer(r"""\b_\(\s*\{([^}]*)\}""", s):
            for v in re.findall(r"""'[^']*'\s*:\s*'([^']*)'""", m.group(1)):
                keys[v] = f.name
        for m in re.finditer(r"""\b_\(\s*'([^']+)'\s+if\s+[^']+else\s+'([^']+)'\s*\)""", s):
            keys[m.group(1)] = keys[m.group(2)] = f.name
    return keys


def test_every_string_in_the_templates_has_a_chinese_version():
    keys = template_keys()
    assert len(keys) > 100
    missing = [f"{k!r} ({f})" for k, f in keys.items() if k not in i18n.ZH]
    assert not missing, missing


def test_every_python_side_ui_string_has_a_chinese_version():
    from core.game import state
    from core.pipelines import train
    from core.storage import model

    need = list(ui.STAGES.values()) + list(model.LEVEL_KEYS.values()) + list(state.TITLES) + list(train.BAD_ACTIONS)
    need += [t for pair in state.BADGES.values() for t in pair if "“" not in t and "boss" not in t]
    need += ["Master of “{label}”", "Beat the {label} boss", "high confidence", "medium confidence", "low confidence", "{k} days ago", "{k} hours ago", "{k} minutes ago", "just now",
             "I spotted {right} of {total} scam messages.", "Can you beat me?", "What is the safest thing to do?", "Nice catch! {tell}"]
    for path in [ROOT / "core/game/engine.py", ROOT / "web/deps.py", ROOT / "web/main.py", *sorted(f for f in (ROOT / "web/routes").glob("*.py") if f.name != "admin.py")]:  # the operator pages stay in English
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) in ("GameError", "HTTPException"):
                need += [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
    missing = [k for k in need if k not in i18n.ZH]
    assert not missing, missing


def test_chinese_entries_keep_their_placeholders():
    from core.lang.i18n_ui import UI_ZH

    for k, v in UI_ZH.items():
        assert set(re.findall(r"\{(\w+)", k)) == set(re.findall(r"\{(\w+)", v)), (k, v)


def test_the_whole_dictionary_converts_to_traditional_cleanly():
    from core.lang.i18n_ui import UI_ZH

    for k, v in UI_ZH.items():
        t = ui.tr(k, "zh-Hant", **{n: "x" for n in re.findall(r"\{(\w+)", k)})
        assert not SIMPLIFIED_ONLY.search(t) and "分鍾" not in t and "複制" not in t, (k, t)


# ------------------------------------------------------------------------------------------------ server text in the visitor's language
def test_a_chinese_scam_checked_with_the_chinese_cookie_returns_a_chinese_result():
    c = lang_client("zh")
    html = c.post("/check", data={"message": SCAM_ZH}).text
    assert html_lang(html) == "zh-Hans" and "这是骗局" in html and "破绽" in html and "该怎么做" in html and "证据（" in html and "红旗" in html and "我是怎么判断的" in html
    assert 'data-say="这是骗局' in html and "朗读" in html and "这个回答对吗？" in html and "练习这种套路" in html
    assert "已加入你的练习：" in html and "催你马上行动" in html  # the tricks are named in Chinese


def test_an_english_message_checked_with_the_chinese_cookie_is_explained_in_chinese():
    html = lang_client("zh").post("/check", data={"message": SCAM_EN}).text
    assert "骗局" in html and "破绽" in html and "The giveaway" not in visible(html)


def test_traditional_results_are_traditional():
    html = lang_client("zh-Hant").post("/check", data={"message": SCAM_ZH}).text
    assert "這是騙局" in html and "破綻" in html and "證據（" in html and "紅旗" in html and "骗" not in html.split("<main")[1]


def test_english_results_are_unchanged():
    html = lang_client("en").post("/check", data={"message": SCAM_EN}).text
    assert "SCAM" in html and "The giveaway" in html and "What to do" in html and "The evidence (" in html and "Red flag" in html and "Read aloud" in html


def test_the_live_view_streams_and_serves_the_result_in_chinese():
    c = lang_client("zh")
    events = []
    with c.stream("POST", "/api/check/stream", json={"message": SCAM_ZH}) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    steps = [e["data"] for e in events if e["type"] == "step"]
    done = [e["data"] for e in events if e["type"] == "done"]
    assert steps and done and any(CJK.search(s["detail"]) for s in steps)
    part = c.get(f"/result/{done[0]}").text
    assert "<html" not in part and "破绽" in part and "证据（" in part and "How I decided" not in part
    assert "我是怎么判断的" in part and ("读取消息" in part or "检查链接和号码" in part)  # the stage names too


def test_the_records_page_speaks_the_visitors_language():
    zh = lang_client("zh")
    zh.post("/check", data={"message": SCAM_ZH})
    html = zh.get("/records").text
    assert "骗局" in html and "刚刚" in html and "网站" in html and "已加入你的练习" in html and "催你马上行动" in html and "just now" not in html
    en = zh.get("/records", headers={"cookie": "lang=en"}).text
    assert "Scam" in en and "just now" in en and "Added to your practice" in en
    hant = lang_client("zh-Hant")
    hant.cookies.set("lang", "zh-Hant")
    page = hant.get("/records").text
    assert "正規公司" in page and "正规公司" not in page  # a record kept in Simplified is shown in Traditional to a Traditional reader


def test_ago_in_both_languages():
    now = datetime.now(timezone.utc)
    ts = lambda **kw: (now - timedelta(**kw)).isoformat()  # noqa: E731
    assert ui.ago(ts(seconds=5)) == "just now" and ui.ago(ts(minutes=1, seconds=5)) == "1 minute ago" and ui.ago(ts(hours=5)) == "5 hours ago" and ui.ago(ts(days=2)) == "2 days ago"
    assert ui.ago(ts(seconds=5), "zh") == "刚刚" and ui.ago(ts(minutes=5), "zh") == "5分钟前" and ui.ago(ts(hours=1, minutes=1), "zh") == "1小时前"
    assert ui.ago(ts(days=3), "zh-Hant") == "3天前" and ui.ago(ts(minutes=5), "zh-Hant") == "5分鐘前"


def test_the_resilience_map_and_its_api_are_translated():
    zh = lang_client("zh").get("/api/map").json()
    assert zh["tactics"][0]["label"] == "催你马上行动" and zh["tactics"][0]["level_text"] == "还没练过"
    en = lang_client("en").get("/api/map").json()
    assert en["tactics"][0]["label"] == "Rushing you" and en["tactics"][0]["level_text"] == "not yet tested"
    assert lang_client("zh-Hant").get("/api/map").json()["tactics"][0]["level_text"] == "還沒練過"
    html = lang_client("zh").get("/train").text
    assert "催你马上行动" in html and "还没练过" in html and "需要加强" in html
    assert "你的防骗能力" not in lang_client("zh").get("/").text  # the map lives on the Train page only


def test_the_due_pill_in_chinese():
    from core.storage import model

    model.record_result("urgency-pressure", "incorrect")
    assert "种套路该复习了" in lang_client("zh").get("/train").text and "due for a refresher" in lang_client("en").get("/train").text


def test_error_messages_follow_the_language():
    zh, en = lang_client("zh"), lang_client("en")
    assert zh.post("/check", data={"message": "   "}).json()["detail"] == "请先贴上要检查的消息。" and en.post("/check", data={"message": "   "}).json()["detail"] == "Paste a message to check."
    assert zh.get("/challenge/nope").json()["detail"] == "找不到这个挑战"
    assert lang_client("zh-Hant").post("/api/game/start", json={"mode": "nope"}).json()["detail"] == "不認識的遊戲模式。"
    assert zh.post("/api/game/start", json={"mode": "nope"}).json()["detail"] == "不认识的游戏模式。" and en.post("/api/game/start", json={"mode": "nope"}).json()["detail"] == "Unknown game mode."
    assert zh.get("/nothing-here").status_code == 404  # an unknown page is still a plain 404


# ------------------------------------------------------------------------------------------------ practice, game, challenge
def test_practice_is_in_chinese_with_chinese_messages():
    c = lang_client("zh")
    s = c.post("/api/train/start").json()
    assert len(s["items"]) == 4 and all(CJK.search(i["scenario"]) and CJK.search(i["question"]) and CJK.search(i["reason"]) for i in s["items"])
    assert all(CJK.search(o) for i in s["items"] for o in i["options"] if i["format"] != "highlight-tell")
    assert s["map"]["tactics"][0]["label"] == "催你马上行动"
    a = c.post("/api/train/answer", json={"session": s["session"], "item_id": s["items"][0]["id"], "choice": 0}).json()
    assert CJK.search(a["note"]) and a["map"]["tactics"][0]["level_text"] in ("需加强", "渐入佳境", "还没练过", "很强")


def test_practice_in_traditional_is_traditional_and_english_is_unchanged():
    s = lang_client("zh-Hant").post("/api/train/start").json()
    assert all(not SIMPLIFIED_ONLY.search(i["question"] + i["reason"] + "".join(i["options"] if i["format"] == "spot-trick" else [])) for i in s["items"])
    e = lang_client("en").post("/api/train/start").json()
    assert all(not CJK.search(i["scenario"] + i["question"] + "".join(i["options"])) for i in e["items"])


def test_the_game_hub_round_and_summary_in_chinese():
    c = lang_client("zh")
    st = c.get("/api/game/state").json()
    assert st["title"] == "新手" and st["tricks"][0]["label"] == "催你马上行动" and CJK.search(st["tricks"][0]["blurb"])
    r = c.post("/api/game/start", json={"mode": "boss", "trick": "urgency-pressure"}).json()
    assert r["trick_label"] == "催你马上行动" and all(CJK.search(i["text"]) for i in r["items"])
    a = c.post("/api/game/answer", json={"round": r["round"], "item_id": r["items"][0]["id"], "choice": "unsure"}).json()
    assert CJK.search(a["tell"]) or a["truth"] == "unsure"
    assert all(CJK.search(t) for t in a["tricks"])
    for it in r["items"][1:]:
        a = c.post("/api/game/answer", json={"round": r["round"], "item_id": it["id"], "choice": "unsure"}).json()
        if a["over"]:
            break
    f = c.post("/api/game/finish", json={"round": r["round"]}).json()
    assert f["trick_label"] == "催你马上行动" and f["badges_new"][0]["title"] == "迈出第一步" and f["state"]["title"] in ("新手", "留心人")
    again = lang_client("zh-Hant").post("/api/game/finish", json={"round": r["round"]}).json()  # the same summary, in Traditional
    assert again["badges_new"][0]["title"] == "邁出第一步" and again["trick_label"] == "催你馬上行動"


def test_the_finished_summary_is_translated_on_every_call_and_english_stays_english():
    c = lang_client("en")
    r = c.post("/api/game/start", json={"mode": "rush"}).json()
    for it in r["items"]:
        c.post("/api/game/answer", json={"round": r["round"], "item_id": it["id"], "choice": "unsure"})
    en = c.post("/api/game/finish", json={"round": r["round"]}).json()
    assert en["badges_new"][0]["title"] == "First steps" and en["state"]["title"] in ("Rookie", "Spotter")
    c.cookies.set("lang", "zh-Hant")
    hant = c.post("/api/game/finish", json={"round": r["round"]}).json()
    assert hant["badges_new"][0]["title"] == "邁出第一步" and hant["state"]["badges"][0]["desc"] == "完成你的第一局"
    c.cookies.set("lang", "en")
    assert c.post("/api/game/finish", json={"round": r["round"]}).json()["badges_new"][0]["title"] == "First steps"


def test_spot_the_tell_works_in_chinese():
    c = lang_client("zh")
    r = c.post("/api/game/start", json={"mode": "tell"}).json()
    assert r["mode"] == "tell" and len(r["items"]) >= 3 and all(i["words"] and CJK.search(i["text"]) for i in r["items"])


def test_a_chinese_challenge_has_chinese_messages_and_english_stays_english():
    zh = lang_client("zh")
    cid = new_challenge(zh)
    items = lambda c, cid: json.loads(unescape(re.search(r"data-items='(.*?)'", c.get(f"/challenge/{cid}").text).group(1)))  # noqa: E731
    assert len(items(zh, cid)) == 6 and all(CJK.search(i["text"]) for i in items(zh, cid))
    en = lang_client("en")
    assert all(not CJK.search(i["text"]) for i in items(en, new_challenge(en)))


def test_the_card_image_accepts_a_language_and_never_fails():
    c = lang_client("en")
    cid = new_challenge(c)
    for q in ("", "&lang=zh", "&lang=zh-Hant", "&lang=xx"):
        png = c.get(f"/card-image/{cid}.png?s=4{q}")
        assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n"


# ------------------------------------------------------------------------------------------------ the share-card image
def test_without_a_chinese_font_the_card_falls_back_to_english_text(monkeypatch):
    monkeypatch.setattr(cardimg, "_font_files", lambda: ())
    cardimg._cjk_choice.cache_clear()
    try:
        assert cardimg.cjk_font("zh", 40, "你好") is None
        assert cardimg.render(67, 4, 6, "zh") == cardimg.render(67, 4, 6, "en")  # English card, not a card full of empty boxes
    finally:
        cardimg._cjk_choice.cache_clear()


def test_a_font_that_lacks_the_characters_is_not_used():
    builtin = cardimg._font(40)
    assert cardimg.has_glyphs(builtin, "Baitproof 67%") and not cardimg.has_glyphs(builtin, "骗局")


def test_the_card_uses_an_installed_chinese_font_when_there_is_one():
    if cardimg.cjk_font("zh", 40, "你能超过我吗？") is None:
        pytest.skip("no Chinese font installed on this machine")
    assert cardimg.render(67, 4, 6, "zh") != cardimg.render(67, 4, 6, "en")
    assert cardimg.render(67, 4, 6, "zh-Hant") != cardimg.render(67, 4, 6, "zh")


def test_font_choice_prefers_the_right_script():
    rank = cardimg._rank
    assert rank("PingFang TC", "Regular", "zh-Hant") > rank("PingFang SC", "Regular", "zh-Hant") > rank("PingFang HK", "Regular", "zh") - 100
    assert rank("PingFang SC", "Regular", "zh") > rank("PingFang TC", "Regular", "zh")
    assert rank("Noto Sans CJK SC", "Regular", "zh") > rank("Noto Sans CJK JP", "Regular", "zh")
    assert rank("Microsoft JhengHei", "Regular", "zh-Hant") > rank("Microsoft YaHei", "Regular", "zh-Hant")
    assert rank("PingFang SC", "Regular", "zh") > rank("PingFang SC", "Light", "zh") and rank(".Hiragino Sans GB Interface", "W3", "zh") < 0


def test_the_apt_packages_for_a_deploy_include_a_chinese_font():
    assert "fonts-noto-cjk" in (ROOT / "deploy/setup_vm.sh").read_text()
