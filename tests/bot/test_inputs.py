"""Screenshots and voice notes in the bot, and the link report in a reply. The readers are fakes (see conftest.py): nothing here calls a model."""
import re

import pytest

from bot import handlers
from core.domain.schemas import CheckResult, LinkInfo, Verdict
from core.inputs import audio, image
from core.inputs.errors import InputError
from core.lang import i18n
from core.lang.i18n_bot import BOT_ZH
from core.lang.i18n_inputs import INPUTS_ZH
from core.obs import logger
from core.storage import history

ZW = handlers.ZWSP
SCAM = "Buy 4 gift cards and send me the numbers please."
PNG = b"\x89PNG\r\n\x1a\n" + b"PICTURE-BYTES-THAT-MUST-NOT-BE-KEPT" * 3


def plain(text: str) -> str:
    return text.replace(ZW, "")


def tappable(text: str) -> bool:
    """Could Telegram turn something in it into a link? Any scheme, or any name.dot.letters with nothing (not even an invisible space) between."""
    return re.search(r"://|[A-Za-z0-9-]\.[A-Za-z]", text) is not None


def fake_result(links=(), **kw) -> CheckResult:
    base = dict(verdict=Verdict.SCAM, headline="🚨 SCAM. Don't pay, don't tap the link.", confidence="high", tell="It asks you to pay with gift cards.",
                action="Don't pay. Phone the company on a number you trust.", check_id="chk-1", links=list(links))
    return CheckResult(**{**base, **kw})


# ---------------------------------------------------------------- a screenshot
def test_a_screenshot_is_read_shown_back_and_then_checked(images):
    replies = handlers.on_image(1001, PNG, "en")
    assert len(replies) == 2
    said, checked = replies
    assert said.text.startswith("📷 I read this from your screenshot:") and f"“{SCAM}”" in said.text and not said.buttons
    assert checked.text.startswith("🚨") and "The giveaway:" in checked.text and "What to do:" in checked.text and "Added to your practice" in checked.text
    assert [b.data for row in checked.buttons for b in row] == ["qn", "ch"]  # the same buttons as after a text check
    assert images.calls == [(PNG, {"lang": "en"})]


def test_links_in_what_was_read_can_never_be_tapped(images):
    images.ok = image.ImageReading(text="DHL: parcel held. Pay the fee at http://dhl-parcel-fee.top/pay?id=7 or www.dhl-parcel.cc/x or dhl-parcel-fee.ru today.\nhttps://bit.ly/3xYz")
    said = handlers.on_image(1002, PNG, "en")[0].text
    assert not tappable(said) and "http://" not in said and ".top" not in said and ".ru" not in said and "bit.ly" not in said
    assert ZW in said and "dhl-parcel-fee.top/pay?id=7" in plain(said) and "dhl-parcel-fee.ru today" in plain(said)  # still reads the same


def test_a_long_text_is_cut_and_the_reply_stays_inside_telegrams_limit(images):
    images.ok = image.ImageReading(text="Please pay now. " * 600)
    said, checked = handlers.on_image(1003, PNG, "en")
    assert 700 < len(said.text) < 800 and "…" in said.text and len(checked.text) <= 4096


def test_the_sender_and_the_readers_note_are_shown(images):
    images.ok = image.ImageReading(text=SCAM, sender="DHL Express +60 12-345 6789", note="The link was hard to read.")
    said = handlers.on_image(1004, PNG, "en")[0].text
    assert "From: DHL Express +60 12-345 6789" in said and said.endswith("The link was hard to read.")


def test_a_hidden_link_in_a_qr_code_is_checked_and_shown_but_not_tappable(images, monkeypatch):
    images.ok = image.ImageReading(text="Scan to claim your parcel", qr_urls=["https://claim-parcel.top/q?x=1"])
    seen = []
    monkeypatch.setattr(handlers, "check_message", lambda text, **kw: seen.append(text) or fake_result())
    said = handlers.on_image(1005, PNG, "en")[0].text
    assert "https://claim-parcel.top/q?x=1" in seen[0] and "Scan to claim your parcel" in seen[0]
    assert "QR code in the picture:" in said and "claim-parcel" in plain(said) and not tappable(said)


def test_a_qr_code_alone_is_enough_to_check(images, monkeypatch):
    images.ok = image.ImageReading(text="", qr_urls=["https://claim-parcel.top/q"])
    monkeypatch.setattr(handlers, "check_message", lambda text, **kw: fake_result())
    replies = handlers.on_image(1006, PNG, "en")
    assert len(replies) == 2 and "“" not in replies[0].text and "QR code in the picture:" in replies[0].text


def test_a_picture_that_is_hard_to_read_is_not_checked(images, monkeypatch):
    images.ok = image.ImageReading(text="Your parc?l is he?d, pay at htt?://d?l.top", legible=False, note="The link was hard to read.")
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: pytest.fail("a blurry picture must not be checked"))
    replies = handlers.on_image(1007, PNG, "en")
    assert len(replies) == 1 and not replies[0].buttons
    t = replies[0].text
    assert t.startswith("📷 I read this from your screenshot:") and "Your parc?l is he?d" in t and "The link was hard to read." in t
    assert "hard to read, so please check this matches what you see" in t and "send a clearer picture, or paste the text" in t
    assert history.list_checks() == []


@pytest.mark.parametrize("reading", [image.ImageReading(text=""), image.ImageReading(text="  \n ", legible=False)])
def test_a_picture_with_no_words_asks_for_a_clearer_one_or_the_text(images, monkeypatch, reading):
    images.ok = reading
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: pytest.fail("nothing to check"))
    replies = handlers.on_image(1008, PNG, "en")
    assert [r.text for r in replies] == ["I couldn't find any words in that picture. Please send a clearer one, or paste the text."]
    assert history.list_checks() == []


# ---------------------------------------------------------------- when reading fails
ERRORS = [("too_big", "That picture is too big. Please send a smaller one."), ("bad_type", "I can only read PNG, JPEG, WebP or GIF pictures."),
          ("unreadable", "I couldn't open that picture. Please send it again."), ("no_text", "I couldn't find any message in that picture."),
          ("too_long", "That is too long for me to read in one go.")]


@pytest.mark.parametrize("code,message", ERRORS)
def test_every_reason_a_picture_cannot_be_read_is_told_kindly_in_the_chats_language(images, monkeypatch, code, message):
    zh = "（中文）" + message
    monkeypatch.setitem(i18n.ZH, message, zh)  # the core's own messages are translated in core/lang/i18n_inputs.py
    images.error = InputError(code, message)
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: pytest.fail("nothing was read"))
    assert [r.text for r in handlers.on_image(1010, PNG, "en")] == [message]
    assert [r.text for r in handlers.on_image(1011, PNG, "zh")] == [zh]
    assert [r.text for r in handlers.on_image(1012, PNG, "zh-hant")] == [i18n.to_traditional(zh)]
    assert history.list_checks() == []


def test_a_picture_over_the_size_limit_is_not_even_sent_to_the_reader(images, monkeypatch):
    monkeypatch.setattr(image, "MAX_BYTES", 1000)
    replies = handlers.on_image(1013, b"x" * 1001, "en")
    assert images.calls == [] and replies[0].text == "That picture is too big (the limit is 0.001 MB). Please send a smaller one, or paste the text."
    assert handlers.on_image(1013, b"x" * 1000, "en")[0].text.startswith("📷") and len(images.calls) == 1


def test_when_screenshots_are_not_switched_on_the_chat_is_told_in_its_language(images, monkeypatch):
    monkeypatch.setattr(image, "available", lambda: False)
    off = "Reading screenshots needs the AI, which is not switched on here. Paste the text instead."
    assert [r.text for r in handlers.on_image(1014, PNG, "en")] == [off]
    assert [r.text for r in handlers.on_image(1015, PNG, "zh")] == [INPUTS_ZH[off]]
    assert images.calls == [] and handlers.RATE == {}  # a request that could not be served does not use up the allowance


def test_a_crash_inside_the_reader_is_a_polite_reply_and_a_log_line_never_a_stack_trace(images):
    images.error = RuntimeError("model endpoint exploded: secret detail")
    replies = handlers.on_image(1016, PNG, "en")
    assert [r.text for r in replies] == ["Sorry, I couldn't read that. Please send the text."]
    assert [r.text for r in handlers.on_image(1017, PNG, "zh")] == ["抱歉，我没能读懂这个。请把文字发给我。"]
    events = open(logger.path(), encoding="utf-8").read()
    assert '"kind":"error"' in events and '"where":"bot.image"' in events and '"type":"RuntimeError"' in events and "secret detail" not in events


# ---------------------------------------------------------------- the same in Chinese
def test_a_screenshot_is_answered_in_the_chats_language(images):
    images.ok = image.ImageReading(text="【顺丰速运】您的快递因地址不详无法派送，请于24小时内点击 http://sf-express-cn.top/addr 补全信息，逾期将退回。", language="zh", sender="顺丰")
    said, checked = handlers.on_image(1020, PNG, "zh")
    assert said.text.startswith("📷 我从你的截图里读到：") and "发件人：顺丰" in said.text and not tappable(said.text)
    assert "骗局" in checked.text.splitlines()[0] and "破绽：" in checked.text
    said, checked = handlers.on_image(1021, PNG, "zh-hant")
    assert said.text.startswith("📷 我從你的截圖裡讀到：") and "騙局" in checked.text.splitlines()[0]


def test_without_a_language_choice_the_reply_follows_the_language_of_the_screenshot(images):
    images.ok = image.ImageReading(text="【顺丰速运】您的快递因地址不详无法派送，请于24小时内点击 http://sf-express-cn.top/addr 补全信息，逾期将退回。", language="zh")
    said, checked = handlers.on_image(1022, PNG, None)
    assert said.text.startswith("📷 我从你的截图里读到：") and "骗局" in checked.text.splitlines()[0]
    images.ok = image.ImageReading(text="", language="zh")
    assert handlers.on_image(1023, PNG, None)[0].text == "我在这张图片里没有找到文字。请发一张更清晰的，或者直接粘贴文字。"


# ---------------------------------------------------------------- the allowance
def test_each_chat_may_read_twenty_pictures_an_hour(images):
    for _ in range(20):
        assert handlers.on_image(1030, PNG, "en")[0].text.startswith("📷")
    stop = handlers.on_image(1030, PNG, "en")
    assert [r.text for r in stop] == ["You've sent a lot of pictures. Please wait a while, or paste the text instead."] and len(images.calls) == 20
    assert [r.text for r in handlers.on_image(1030, PNG, "zh")] == ["你发了好多图片了。请稍等一会儿，或者直接粘贴文字。"]
    assert handlers.on_image(1031, PNG, "en")[0].text.startswith("📷")  # another chat is not affected
    handlers.RATE["image:1030"] = [t - 3601 for t in handlers.RATE["image:1030"]]  # an hour later
    assert handlers.on_image(1030, PNG, "en")[0].text.startswith("📷")


def test_pictures_and_voice_notes_have_separate_allowances(images, voices):
    for _ in range(20):
        handlers.on_image(1032, PNG, "en")
    assert handlers.on_image(1032, PNG, "en")[0].text.startswith("You've sent a lot of pictures")
    assert handlers.on_voice(1032, b"ogg", "audio/ogg", "en")[0].text.startswith("🎙️ I heard:")
    for _ in range(19):
        handlers.on_voice(1032, b"ogg", "audio/ogg", "en")
    assert [r.text for r in handlers.on_voice(1032, b"ogg", "audio/ogg", "en")] == ["You've sent a lot of voice notes. Please wait a while, or send the text instead."]
    assert len(voices.calls) == 20


def test_the_checks_made_before_downloading_do_not_use_up_the_allowance(images, voices, monkeypatch):
    for _ in range(30):
        assert handlers.image_precheck(1033, 1000, "en") == [] and handlers.voice_precheck(1033, 1000, 5, "en") == []
    assert handlers.RATE == {}
    for _ in range(20):
        handlers.on_image(1033, PNG, "en")
    assert handlers.image_precheck(1033, 1000, "en")[0].text.startswith("You've sent a lot of pictures")  # but it sees a full allowance
    monkeypatch.setattr(image, "MAX_BYTES", 10)
    assert handlers.image_precheck(1034, 11, "en")[0].text.startswith("That picture is too big") and handlers.image_precheck(1034, None, "en") == []


# ---------------------------------------------------------------- records and privacy
def test_a_checked_screenshot_is_recorded_like_a_text_check_from_the_words_that_were_read(images):
    images.ok = image.ImageReading(text="Call me on +60 12-345 6789 or pay at http://dhl-parcel-fee.top/pay?id=7 now. " + SCAM)
    handlers.on_image(1040, PNG, "en")
    rows = history.list_checks()
    assert len(rows) == 1 and rows[0]["channel"] == "telegram" and rows[0]["verdict"] in ("scam", "likely_scam")
    assert "dhl-parcel-fee.top" in rows[0]["preview"] and "/pay?id=7" not in rows[0]["preview"] and "345" not in rows[0]["preview"]  # redacted as usual
    assert "gift cards" in rows[0]["preview"] and "📷" not in rows[0]["preview"]
    assert "dhl-parcel-fee.top" in handlers.on_history(1040)  # and /history shows it


def test_the_picture_itself_is_never_kept(images, tmp_path):
    handlers.on_image(1041, PNG, "en")
    marker = b"PICTURE-BYTES-THAT-MUST-NOT-BE-KEPT"
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert marker not in f.read_bytes(), f
    assert any(f.name.endswith(".sqlite") for f in tmp_path.iterdir())  # the database was searched too
    assert all(marker not in r.text.encode() for r in handlers.on_image(1041, PNG, "en"))


def test_what_the_pipeline_is_told_about_the_source_depends_on_what_it_accepts(images, monkeypatch):
    got = {}

    def new_style(text, store=True, on_event=None, log=True, lang=None, source="text", read_text=""):
        got.update(text=text, source=source, read_text=read_text, lang=lang)
        return fake_result()

    monkeypatch.setattr(handlers, "check_message", new_style)
    handlers.on_image(1042, PNG, "en")
    assert got == {"text": SCAM, "source": "screenshot", "read_text": SCAM, "lang": "en"}

    done = []

    def old_style(text, store=True, on_event=None, log=True, lang=None):
        done.append(fake_result())
        return done[-1]

    monkeypatch.setattr(handlers, "check_message", old_style)  # a pipeline that does not know about sources yet: the bot sets them itself
    handlers.on_image(1043, PNG, "en")
    assert done[0].source == "screenshot" and done[0].read_text == SCAM
    handlers.on_text(1044, SCAM)  # and plain text is untouched
    assert done[1].source == "text" and done[1].read_text == ""


# ---------------------------------------------------------------- a voice note
def test_a_voice_note_is_heard_shown_back_and_then_checked(voices):
    said, checked = handlers.on_voice(1050, b"OggS-audio", "audio/ogg", "en")
    assert said.text == f"🎙️ I heard:\n\n“{SCAM}”" and checked.text.startswith("🚨") and [b.data for row in checked.buttons for b in row] == ["qn", "ch"]
    assert voices.calls == [(b"OggS-audio", {"mime": "audio/ogg", "lang_hint": ""})]
    rows = history.list_checks()
    assert len(rows) == 1 and rows[0]["channel"] == "telegram" and "gift cards" in rows[0]["preview"]


def test_what_was_heard_is_defanged_and_answered_in_chinese(voices):
    voices.ok = audio.Transcript(text="请打开 www.sf-express-cn.top 然后输入验证码 482913，快点。", language="zh")
    said, checked = handlers.on_voice(1051, b"ogg", "audio/ogg", "zh")
    assert said.text.startswith("🎙️ 我听到的是：") and "sf-express-cn" in plain(said.text) and not tappable(said.text)
    assert "这是骗局" in checked.text or "很可能" in checked.text or "不确定" in checked.text


def test_voice_notes_that_are_not_switched_on_are_explained_in_the_chats_language(voices, monkeypatch):
    monkeypatch.setattr(audio, "available", lambda: False)
    off = "Voice notes are not switched on here. Send the text or a screenshot instead."
    assert [r.text for r in handlers.on_voice(1052, b"ogg", "audio/ogg", "en")] == [off]
    assert [r.text for r in handlers.on_voice(1053, b"ogg", "audio/ogg", "zh")] == ["这里没有开启语音消息。请发送文字或截图。"]
    assert [r.text for r in handlers.voice_precheck(1054, 100, 5, "en")] == [off] and voices.calls == []


def test_a_voice_note_over_the_size_or_length_limit_is_refused_before_it_is_downloaded(voices, monkeypatch):
    monkeypatch.setattr(audio, "MAX_BYTES", 5_000_000)
    monkeypatch.setattr(audio, "MAX_SECONDS", 60)
    assert handlers.voice_precheck(1055, 5_000_000, 60, "en") == []
    big = handlers.voice_precheck(1055, 5_000_001, 10, "en")[0].text
    assert big == "That voice note is too big (the limit is 5 MB). Please send a shorter one, or the text."
    assert handlers.voice_precheck(1055, 100, 61, "zh")[0].text == "这条语音太长了（上限 60 秒）。请发一条短一点的，或者直接发文字。"
    assert handlers.on_voice(1055, b"x" * 5_000_001, "audio/ogg", "en")[0].text == big and voices.calls == []


@pytest.mark.parametrize("code,message", ERRORS)
def test_every_reason_a_voice_note_cannot_be_heard_is_told_kindly(voices, monkeypatch, code, message):
    monkeypatch.setitem(i18n.ZH, message, "（中文）" + message)
    voices.error = InputError(code, message)
    assert [r.text for r in handlers.on_voice(1056, b"ogg", "audio/ogg", "en")] == [message]
    assert [r.text for r in handlers.on_voice(1057, b"ogg", "audio/ogg", "zh")] == ["（中文）" + message]
    assert history.list_checks() == []


def test_a_voice_note_with_no_words_and_a_crash_are_handled(voices, monkeypatch):
    voices.ok = audio.Transcript(text="  ")
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: pytest.fail("nothing was heard"))
    assert [r.text for r in handlers.on_voice(1058, b"ogg", "audio/ogg", "en")] == ["I couldn't hear any words in that voice note. Please try again, or send the text."]
    assert handlers.on_voice(1058, b"ogg", "audio/ogg", "zh")[0].text == "我没有在这条语音里听到文字。请再试一次，或者直接发文字。"
    voices.error = ValueError("decoder fell over")
    assert [r.text for r in handlers.on_voice(1059, b"ogg", "audio/ogg", "en")] == ["Sorry, I couldn't read that. Please send the text."]
    assert '"where":"bot.voice"' in open(logger.path(), encoding="utf-8").read()


def test_the_voice_note_is_never_kept(voices, tmp_path):
    voices.ok = audio.Transcript(text=SCAM)
    handlers.on_voice(1060, b"AUDIO-BYTES-THAT-MUST-NOT-BE-KEPT" * 4, "audio/ogg", "en")
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert b"AUDIO-BYTES-THAT-MUST-NOT-BE-KEPT" not in f.read_bytes(), f


# ---------------------------------------------------------------- the link report
LINKS = [LinkInfo(host="dhl.com", status="official", label="The real DHL website"),
         LinkInfo(host="dhl-parcel.top", status="lookalike", label="Looks like DHL but isn't"),
         LinkInfo(host="bit.ly", status="shortener", label="A short link", expanded_to="evil-pay.xyz"),
         LinkInfo(host="1.2.3.4", status="suspicious", label="A bare number address"),
         LinkInfo(host="mystery.example", status="unverified"),
         LinkInfo(host="bbc.co.uk", status="established", label="Online for over 20 years")]


def test_the_reply_lists_each_link_with_an_emoji_the_address_that_cannot_be_tapped_and_where_a_short_link_leads(monkeypatch):
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: fake_result(LINKS[:5]))
    text = handlers.on_text(1070, "see the links")
    block = text.split("\n\n")[3]  # headline, giveaway, what to do, then the links
    lines = [plain(line) for line in block.splitlines()]
    assert lines == ["🔗 Links",
                     "✅ dhl.com — The real DHL website",
                     "⚠️ dhl-parcel.top — Looks like DHL but isn't",
                     "🔗 bit.ly — A short link → really goes to evil-pay.xyz",
                     "🚫 1.2.3.4 — A bare number address",
                     "❓ mystery.example"]
    assert not tappable(block) and "1.2.3.4" not in block and ZW in block
    assert text.startswith("🚨") and text.index("What to do:") < text.index("🔗 Links")


def test_the_links_come_before_the_practice_line_and_the_established_site_has_its_own_emoji(monkeypatch):
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: fake_result([LINKS[5]], added_to_training=["urgency-pressure"]))
    text = handlers.on_text(1071, "x")
    assert "🏛️ bbc.co.uk — Online for over 20 years" in plain(text) and text.index("🔗 Links") < text.index("📚 Added to your practice")


def test_a_link_on_the_public_phishing_list_gets_the_stop_sign(monkeypatch):
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: fake_result([LinkInfo(host="pay-now-parcel.top", status="known_phishing", label="Known phishing website")]))
    text = plain(handlers.on_text(1075, "see the link"))
    assert "🚫 pay-now-parcel.top — Known phishing website" in text.replace(ZW, "")


def test_a_reply_with_no_links_has_no_links_section(monkeypatch):
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: fake_result())
    assert "🔗" not in handlers.on_text(1072, "x")
    assert "🔗" not in handlers.on_text(1073, "Buy 4 gift cards and send me the numbers please.")


def test_a_long_list_of_links_is_cut_to_five_and_the_rest_counted_and_the_reply_still_fits(monkeypatch):
    many = [LinkInfo(host=f"scam-{i}.top", status="suspicious", label="x" * 300) for i in range(40)]
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: fake_result(many, tell="word " * 2000, added_to_training=["urgency-pressure"]))
    text = handlers.on_text(1074, "x")
    assert text.count("🚫") == 5 and "…and 35 more link(s)" in text and len(text) <= 4000
    assert text.rstrip().splitlines()[-1].startswith("📚 Added to your practice")  # the end survives; it is the giveaway that gets cut


def test_the_link_report_follows_the_reply_language(monkeypatch):
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: fake_result([LINKS[2]], lang="zh"))
    text = plain(handlers.on_text(1075, "x"))
    assert "🔗 链接" in text and "→ 实际指向 evil-pay.xyz" in text


def test_the_link_report_is_part_of_a_screenshot_check_too(images, monkeypatch):
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: fake_result(LINKS[:2]))
    checked = handlers.on_image(1076, PNG, "en")[1].text
    assert "🔗 Links" in checked and "⚠️" in checked and not tappable(checked)


def test_a_link_quoted_in_the_giveaway_or_the_advice_is_not_tappable_either_and_other_dots_are_left_alone(monkeypatch):
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: fake_result(
        tell="It sends you to dhl-parcel-fee.top/pay or www.dhl-parcel.cc, e.g. for a fee of 2.99.", action="Do not open http://dhl-parcel-fee.top/pay or bit.ly/3xYz."))
    text = handlers.on_text(1077, "x")
    assert "http://" not in text and "fee.top" not in text and "www.dhl" not in text and "bit.ly" not in text and ZW in text
    assert "dhl-parcel-fee.top/pay or www.dhl-parcel.cc" in plain(text) and "e.g. for a fee of 2.99." in text  # still reads the same; 'e.g.' and '2.99' untouched


def test_an_unknown_link_status_still_gets_a_line():
    out = handlers.format_links([LinkInfo(host="odd.example", status="brand-new")], "en")
    assert plain(out) == "🔗 Links\n❓ odd.example"


# ---------------------------------------------------------------- wording
def test_the_welcome_mentions_screenshots_and_voice_notes():
    assert "You can also send a screenshot or a voice note." in handlers.on_start(1080)
    handlers.on_lang(1081, "zh")
    assert "你也可以直接发截图或语音消息给我。" in handlers.on_start(1081)


def test_the_bots_new_wording_does_not_collide_with_the_readers():
    assert not set(BOT_ZH) & set(INPUTS_ZH)


# ---------------------------------------------------------------- where it came from
def capture_origin(monkeypatch):
    got = {}

    def fake(text, **kw):
        got.update(kw)
        return fake_result(origin=kw.get("origin"), origin_note="Where it came from: a screen inside Tomoro Coffee" if kw.get("origin") else "")
    monkeypatch.setattr(handlers, "check_message", fake)
    return got


def test_a_screenshot_hands_the_pipeline_what_the_picture_showed_and_the_reply_says_it(images, monkeypatch):
    got = capture_origin(monkeypatch)
    images.ok = image.ImageReading(text="Voucher Applied APP | PAYDAY REWARDS 1-FOR-1", sender="", channel="app", app="Tomoro Coffee")
    replies = handlers.on_image(1301, PNG, "en")
    assert got["origin"].channel == "app" and got["origin"].app == "Tomoro Coffee"
    assert "📍 Where it came from: a screen inside Tomoro Coffee" in plain(replies[-1].text)


def test_a_forward_tells_the_pipeline_who_it_was_forwarded_from(monkeypatch):
    got = capture_origin(monkeypatch)
    handlers.on_check(1302, "Win a prize now", None, "Daily Deals")
    assert got["origin"].forwarded_from == "Daily Deals"
    got.clear()
    handlers.on_check(1303, "Win a prize now")
    assert "origin" not in got  # typed or pasted in: nothing is claimed about where it came from


def test_the_origin_line_can_never_be_tapped(monkeypatch):
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: fake_result(origin_note="Where it came from: a screen inside dhl-fee.xyz"))
    text = handlers.on_text(1304, "x")
    assert "📍" in text and not tappable(text.split("📍")[1].split("\n")[0])


def test_a_safe_answer_says_what_it_rests_on(monkeypatch):
    from core.domain.schemas import Evidence
    proof = Evidence(kind="tool", source="org-verified", supports="safe", strength="medium", claim="Tomoro Coffee is a real, known organisation, and this message asks for nothing and points nowhere")
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: fake_result(verdict=Verdict.SAFE, evidence=[proof]))
    text = plain(handlers.on_text(1305, "x"))
    assert "🔎 What I checked: Tomoro Coffee is a real, known organisation" in text
    monkeypatch.setattr(handlers, "check_message", lambda *a, **k: fake_result(verdict=Verdict.SCAM, evidence=[proof]))
    assert "🔎" not in handlers.on_text(1306, "x")  # only a safe answer needs to justify itself
