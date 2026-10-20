from bot import handlers
from core.storage import model


def test_bot_check_and_score(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    out = handlers.on_text(111, "Buy 4 gift cards and send me the numbers please.")
    assert out.startswith("🚨") and "giveaway" in out and "Added to your practice" in out
    assert "score" in handlers.on_score(111).lower()
    # a different chat has its own, untouched profile
    assert "Weakest" not in handlers.on_score(222) and model.baitproof_score() == 0
    assert handlers.on_text(111, "   ") == "Send me the message you want checked."


def test_nudge_only_when_due(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    assert handlers.nudge_text(5) is None
    handlers.bind_chat(5)
    model.record_result("urgency-pressure", "incorrect")  # incorrect => due immediately
    assert "due" in handlers.nudge_text(5)


def test_bot_answers_in_the_users_language(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    scam = "【顺丰速运】您的快递因地址不详无法派送，请于24小时内点击 http://sf-express-cn.top/addr 补全信息，逾期将退回。"
    zh = handlers.on_text(901, scam)  # no preference: the message's own language
    assert zh.startswith("🚨") and "骗局" in zh.splitlines()[0] and "破绽：" in zh and "该怎么做：" in zh and "已加入你的练习" in zh
    en = handlers.on_text(902, scam, lang_hint="en")  # Telegram says this user reads English
    assert "SCAM" in en.splitlines()[0] and "The giveaway:" in en and "破绽" not in en
    hant = handlers.on_text(903, scam, lang_hint="zh-hant")
    assert "騙局" in hant.splitlines()[0] and "破綻：" in hant


def test_lang_command_is_remembered_per_chat(monkeypatch):
    monkeypatch.setenv("BAITPROOF_MULTIUSER", "1")
    assert "English" in handlers.on_lang(910, "en")
    assert handlers.on_lang(911, "zh") == "已切换为简体中文。" and handlers.on_lang(912, "zh-Hant") == "已切換為繁體中文。"
    assert "/lang" in handlers.on_lang(913, "klingon")
    scam = "Buy 4 gift cards and send me the numbers please."
    assert "骗局" in handlers.on_text(911, scam).splitlines()[0]            # chose Simplified Chinese: even an English message is explained in Chinese
    assert "SCAM" in handlers.on_text(910, scam).splitlines()[0]
    assert handlers.on_start(911).startswith("你好！我是 Baitproof") and handlers.on_start(910).startswith("Hi! I'm Baitproof")
    assert "分数" in handlers.on_score(911) and "score" in handlers.on_score(910).lower()
    assert "最近的检查" in handlers.on_history(911) and "Your latest checks" in handlers.on_history(910)
