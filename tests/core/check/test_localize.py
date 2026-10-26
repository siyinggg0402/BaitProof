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
    return {"items": [f"中文翻译：{x[:6]}" for x in req["items"]]}


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


def test_an_explanation_copied_from_the_prompts_own_example_is_replaced(monkeypatch):
    fake(monkeypatch, translate=zh_of, tell="Your parcel is on hold. Pay 1.45 at dpd-fee.top", action="Do not click. Call SF Express on its real number.")
    r = check_message(PARCEL, store=False, log=False)
    assert "dpd-fee" not in r.tell and "1.45" not in r.tell and r.tell                      # our own wording for the trick instead
    assert r.verdict == V.SCAM and any("没有的内容" in t.detail for t in r.trace if t.stage == "output")


def test_chinese_means_mostly_chinese_not_one_chinese_word_in_an_english_sentence():
    assert localize.mostly_chinese("它说你必须在24小时内点击链接，否则包裹会被退回。")
    assert localize.mostly_chinese("请登录 icbc-verify-cn.top 验证身份")            # (a web address in a Chinese sentence)
    assert localize.mostly_chinese("请联系 DHL 的官方客服")
    assert not localize.mostly_chinese("It says you must click within 24小时内 or the parcel will be returned.")
    assert not localize.mostly_chinese("Do not click the link. Contact 顺丰速运 using the phone number on their official website.")
    assert not localize.mostly_chinese("") and not localize.in_script("Contact 顺丰速运 using the number on their site.", "zh")


def test_an_english_sentence_with_a_chinese_quote_is_still_translated(monkeypatch):
    calls = fake(monkeypatch, translate=zh_of, tell="It says you must click within 24小时内 or the parcel will be returned.", action="Do not click. Contact 顺丰速运 on its real number.")
    r = check_message(PARCEL, store=False, log=False)
    assert calls["translate"] == 1 and r.tell.startswith("中文翻译：") and r.action.startswith("中文翻译：")


def test_a_company_the_model_names_in_english_is_caught_after_translation(monkeypatch):
    bank = "【中国工商银行】您的账户存在异常，已被临时冻结。请立即登录 http://icbc-verify-cn.top 验证身份，否则账户将被永久冻结。"
    fake(monkeypatch, translate=lambda req: {"items": ["请使用卡片背面的电话号码联系中国建设银行。" for _ in req["items"]]},
         tell="Your account is frozen and you must log in at once.", action="Call China Construction Bank on the number on your card.")
    r = check_message(bank, store=False, log=False)
    assert "建设银行" not in r.tell + r.action and r.action and any("没有的内容" in t.detail for t in r.trace if t.stage == "output")
