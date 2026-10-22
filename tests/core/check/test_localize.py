"""The reader gets the model's sentences in their own language. Offline: the model is faked."""
import json
import re

from core.ai import llm
from core.domain.schemas import Verdict as V
from core.pipelines.check import check_message, localize

CJK = re.compile(r"[一-鿿]")
PARCEL = "【顺丰速运】您的快递因地址不详无法派送，请于24小时内点击 http://sf-express-cn.top/addr 补全信息，逾期将退回。"


def fake(monkeypatch, *, translate=None, tell="It says you must click a link within 24 hours or the parcel is returned.", action="Do not click. Call SF Express on its real number.",
         why="The link looks like the real SF Express site but is slightly off."):
    calls = {"translate": 0}

    def chat_json(system, user, heavy=True, retries=1, **kw):
        if "translate short sentences" in system:
            calls["translate"] += 1
            if translate is None:
                raise llm.LLMUnavailable("down")
            return translate(json.loads(user))
        if "diagnose" in system or "classify what a message is FOR" in system:
            return {"asks": [], "pressure": []}
        if "second reviewer" in system:
            return {"concern": False}
        return {"verdict": "scam", "tactics": [{"id": "lookalike-link", "quote": "http://sf-express-cn.top/addr", "why": why}], "the_tell": tell, "action": action}

    monkeypatch.setattr(llm, "chat_json", chat_json)
    monkeypatch.setattr(llm, "available", lambda: True)
    return calls


def zh_of(req):  # a stand-in for the model's translation: marks each item as Chinese
    return {"items": [f"中文：{x[:12]}" for x in req["items"]]}


def test_english_sentences_for_a_chinese_reader_are_translated_in_one_call(monkeypatch):
    calls = fake(monkeypatch, translate=zh_of)
    r = check_message(PARCEL, store=False, log=False)
    assert r.lang == "zh" and calls["translate"] == 1
    assert CJK.search(r.tell) and CJK.search(r.action)
    assert any(CJK.search(e.claim) for e in r.evidence if e.kind == "model" and e.source == "analysis")


def test_nothing_is_translated_when_the_model_already_wrote_chinese(monkeypatch):
    calls = fake(monkeypatch, translate=zh_of, tell="地址不详，要求24小时内点击链接。", action="不要点，直接打电话核实。", why="网址和顺丰的官方网站很像，但有细微差别。")
    r = check_message(PARCEL, store=False, log=False)
    assert calls["translate"] == 0 and r.tell.startswith("地址不详")


def test_if_the_translation_fails_the_static_chinese_text_is_used(monkeypatch):
    fake(monkeypatch, translate=None)  # the translation call raises
    r = check_message(PARCEL, store=False, log=False)
    assert CJK.search(r.tell) and CJK.search(r.action) and "link" not in r.tell.lower()
    assert all(CJK.search(e.claim) for e in r.evidence if e.kind == "model" and e.source == "analysis")


def test_a_bad_translation_answer_is_never_half_used(monkeypatch):
    fake(monkeypatch, translate=lambda req: {"items": ["只有一个"]})  # wrong length
    r = check_message(PARCEL, store=False, log=False)
    assert CJK.search(r.tell) and "link" not in r.tell.lower()  # the static text, not a mix


def test_english_readers_cost_no_extra_call(monkeypatch):
    calls = fake(monkeypatch, translate=zh_of)
    r = check_message("DHL: Your parcel is on hold. Pay the $1.99 fee within 24 hours. Pay now: dhl-fee-pay.xyz/track", store=False, log=False)
    assert r.lang == "en" and calls["translate"] == 0 and r.verdict in (V.SCAM, V.LIKELY_SCAM)


def test_a_chinese_message_explained_in_english_is_left_alone(monkeypatch):
    calls = fake(monkeypatch, translate=zh_of)
    r = check_message(PARCEL, store=False, log=False, lang="en")
    assert r.lang == "en" and calls["translate"] == 0 and not CJK.search(r.action)


def test_the_script_follows_the_reader(monkeypatch):
    assert localize.convert_script("这是骗局，请点击链接", "zh-Hant") == "這是騙局，請點擊連結"
    assert localize.convert_script("這是騙局，請點擊", "zh") == "这是骗局，请点击"
    assert localize.convert_script("plain English", "zh") == "plain English"
