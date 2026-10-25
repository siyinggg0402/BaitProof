"""Malay (Bahasa Melayu): every Chinese-translated string has a Malay one with the same blanks, the tactics are explained, and answers come out in Malay. The Malay practice bank (data/seeds/ms.json): well-formed, in Malay, not leaked into the evaluation sets, and the rules never clear a scam in it. Malay and Indonesian rules (no model). The two sets are authored (see their docstrings): ms/holdout.py was a first reading, ms/fresh.py was written after
the rules existed and was then used to fix the gaps it exposed, so both now count as development sets."""
import re

import pytest

from core.domain.schemas import Verdict as V
from core.domain.tactics import TACTICS
from core.domain.tactics import valid
from core.game import pool as gp
from core.lang import i18n
from core.lang.i18n import MS, TACTICS_MS, ZH, from_accept_language, norm, tactic_text, tr
from core.lang.text import detect
from core.lang.text import CURRENT, Dual
from core.pipelines.check import check_message
from core.pipelines.check.pipeline import reply_language
from core.storage import library
from tests.data.ms import fresh as ms_fresh, holdout as ms_holdout


CJK = re.compile(r"[一-鿿]")
BLANK = re.compile(r"\{[^{}]*\}")
PRIZE = "Tahniah! Anda telah memenangi hadiah RM50,000. Sila klik pautan ini untuk menuntut dalam 24 jam http://hadiah-maybank.top/tuntut"
DHL = "DHL: Your parcel is on hold. Pay the $1.99 fee within 24 hours. Pay now: dhl-fee-pay.xyz/track"


@pytest.mark.parametrize("raw", ["ms", "ms-MY", "ms_SG", "MS", "bm", "malay", "bahasa", "bahasa-melayu"])
def test_malay_codes_are_recognised(raw):
    assert norm(raw) == "ms"


def test_accept_language_can_pick_malay():
    assert from_accept_language("ms-MY,ms;q=0.9,en;q=0.5") == "ms"
    assert from_accept_language("fr-FR,ms;q=0.8") == "ms"
    assert from_accept_language("en-US,en;q=0.9,ms;q=0.5") == "en"


def test_every_translated_string_has_a_malay_version_and_none_is_an_orphan():
    assert not [k for k in ZH if k not in MS], "add a Malay version in core/lang/i18n_ms.py"
    assert not [k for k in MS if k not in ZH], "a Malay string whose English key matches nothing (a typo?)"


def test_malay_keeps_the_blanks_and_line_breaks_of_the_english():
    bad = [k for k, v in MS.items() if sorted(BLANK.findall(k)) != sorted(BLANK.findall(v)) or k.count("\n") != v.count("\n")]
    assert not bad, bad[:5]


def test_malay_is_not_left_in_chinese_or_in_english():
    names = re.compile("|".join(re.escape(n) for n in i18n.NAMES.values()))
    assert not [k for k, v in MS.items() if CJK.search(names.sub("", v))]  # (the language menu names Chinese in Chinese, on purpose)
    same = {k for k, v in MS.items() if v == k}
    assert len(same) < 40, sorted(same)  # a few brands and symbols are written the same in every language; a long list means untranslated text


def test_every_tactic_is_explained_in_malay():
    assert set(TACTICS_MS) == set(TACTICS)
    for tid, parts in TACTICS.items():
        for field in ("label", "blurb", "tell", "action"):
            got = tactic_text(tid, field, "ms", TACTICS)
            assert got and got != parts[field] and not CJK.search(got), (tid, field)


def test_malay_text_is_filled_in_and_unknown_text_falls_back_to_english():
    assert tr("{n} separate red flags", "ms", n=3) == MS["{n} separate red flags"].format(n=3) and "3" in tr("{n} separate red flags", "ms", n=3)
    assert tr("a sentence nobody translated", "ms") == "a sentence nobody translated"
    assert tr("Read aloud", "zh-Hant") != tr("Read aloud", "ms")  # a different language, not the Chinese one converted


def test_reply_language_for_malay():
    assert reply_language("Tahniah anda menang hadiah", None) == "ms"
    assert reply_language("Tahniah anda menang hadiah", "en") == "en"           # a Malay message, an English reader
    assert reply_language("Your parcel is on hold", "ms") == "ms"               # a Malay reader checking an English message


def test_a_malay_message_gets_a_malay_answer():
    r = check_message(PRIZE, store=False, log=False)
    assert r.lang == "ms" and r.message_lang == "ms" and r.verdict in (V.SCAM, V.LIKELY_SCAM)
    assert r.headline.startswith("🚨") and "PENIPUAN" in r.headline.upper()
    assert ": " in r.tell and "：" not in r.tell  # Malay is punctuated like English, not like Chinese
    assert not CJK.search(r.headline + r.tell + r.action + " ".join(e.claim for e in r.evidence))
    assert any("frasa penipuan" in e.claim for e in r.evidence)


def test_an_english_message_is_explained_in_malay_when_asked_and_quotes_stay_in_english():
    r = check_message(DHL, store=False, log=False, lang="ms")
    assert r.lang == "ms" and r.message_lang == "en" and "PENIPUAN" in r.headline.upper()
    assert any("“within 24 hours”" in e.claim and "frasa penipuan" in e.claim for e in r.evidence)  # the quote is the sender's words; the rest is ours


def test_english_answers_are_untouched_by_malay():
    r = check_message(DHL, store=False, log=False)
    assert r.lang == "en" and "SCAM" in r.headline.upper() and "PENIPUAN" not in r.headline.upper()


def test_a_malay_victim_gets_support_in_malay():
    r = check_message("Saya ditipu, saya sudah beri kod OTP kepada mereka", store=False, log=False)
    assert r.verdict is V.VICTIM and r.lang == "ms" and "bukan salah anda" in r.headline


def test_the_help_lines_are_in_malay():
    from core.domain import helplines
    text = helplines.text("ms")
    assert "1799" in text and "997" in text and "Singapura" in text and "Hubungi bank anda" in text and "Oktober 2026" in text and "October" not in text
    assert helplines.short("ms") != helplines.short("en") and "1799" in helplines.short("ms") and "997" in helplines.short("ms")


def test_the_steps_of_a_check_read_as_finished_work():
    for key in ("Read the message", "Checked links and numbers", "Weighed the evidence"):
        assert tr(key, "ms").startswith("Telah ")
    assert "ms" in i18n.LANGS and i18n.NAMES["ms"] == "Bahasa Melayu"


def test_malay_seed_bank_is_well_formed():
    seeds = library.seed_examples("ms")
    assert len(seeds) >= 40 and len({e["id"] for e in seeds}) == len(seeds)
    assert sum(e["is_scam"] for e in seeds) >= 28 and sum(not e["is_scam"] for e in seeds) >= 12
    for e in seeds:
        assert detect(e["text"]) == "ms" and e["tell"] and e["action"], e["id"]
        if e["is_scam"]:
            assert e["tactics"] and all(valid(t) for t in e["tactics"]) and e["tell_phrase"] and e["tell_phrase"] in e["text"], e["id"]
        else:
            assert not e["tactics"] and not e["tell_phrase"], e["id"]


def test_the_malay_bank_does_not_leak_into_the_evaluation_sets():
    texts = {e["text"] for e in library.seed_examples("ms")}
    assert not texts & {t for _, t in ms_holdout.SCAMS + ms_holdout.LEGIT + ms_fresh.SCAMS + ms_fresh.LEGIT}


def test_the_other_banks_are_unchanged_by_the_malay_one():
    assert len(library.seed_examples()) == 42 and not any(detect(e["text"]) == "ms" for e in library.seed_examples())
    assert not any(detect(e["text"]) == "ms" for e in library.seed_examples("zh"))


def test_rules_alone_never_clear_a_malay_scam_and_flag_no_genuine_seed():
    seeds = library.seed_examples("ms")
    verdicts = [(e, check_message(e["text"], store=False, log=False).verdict) for e in seeds]
    assert not [e["id"] for e, v in verdicts if e["is_scam"] and v is V.SAFE]
    assert not [e["id"] for e, v in verdicts if not e["is_scam"] and v in (V.SCAM, V.LIKELY_SCAM)]
    caught = sum(v in (V.SCAM, V.LIKELY_SCAM) for e, v in verdicts if e["is_scam"])
    assert caught / sum(e["is_scam"] for e in seeds) >= 0.85, caught


def test_a_malay_round_is_played_on_malay_messages_with_all_three_answers():
    unsure = [e for e in library.seed_examples("ms") if e.get("truth") == "unsure"]
    assert len(unsure) >= 4 and all(not e["is_scam"] and not e["tactics"] and e["tell"] and e["action"] for e in unsure)
    ms = gp.build_pool("ms")
    assert ms and all(detect(i.text) == "ms" for i in ms if i.source == "seed") and not any(i.source == "bank" for i in ms)  # the English authored bank stays out
    assert sum(i.truth == "unsure" for i in ms if i.source == "seed") == len(unsure)
    assert {i.source for i in gp.build_pool("en")} >= {"seed", "bank"}


def test_malay_words_are_tappable_like_english():
    assert gp.words("Bayar dalam masa 24 jam sekarang") == ["Bayar", "dalam", "masa", "24", "jam", "sekarang"]


def test_a_chinese_scam_from_their_own_circle_is_explained_in_malay_not_in_chinese(monkeypatch):
    """Someone who checks Chinese messages and reads Malay: the message stays as it was written, but what we say about it is Malay."""
    from core.pipelines import train

    assert train.localized("礼品卡、加密货币和电汇是骗子收钱的方式。", "irreversible-payment", "tell", "ms") == "Kad hadiah, kripto dan pindahan wang ialah cara penipu menerima bayaran. Bil sebenar tidak pernah menggunakannya."
    assert train.localized("Nothing here is a trick.", "irreversible-payment", "tell", "ms") == "Nothing here is a trick."  # (anything that is not Chinese is kept)
    assert train.localized("礼品卡", "", "tell", "ms") == ""
    chinese = {"id": "u1", "source": "user", "is_scam": True, "text": "【顺丰】请于24小时内点击链接补全信息。", "tactics": ["urgency-pressure"],
               "tell_phrase": "24小时内", "tell": "正规公司会给你时间。", "action": "先停下来。"}
    malay = {"id": "u2", "source": "user", "is_scam": True, "text": "Pos Laju: bungkusan anda ditahan. Sila bayar yuran di http://poslaju-bayar.top sekarang.", "tactics": ["urgency-pressure"],
             "tell_phrase": "sekarang", "tell": "正规公司会给你时间。", "action": "先停下来。"}  # a Malay message checked while the site was in Chinese: its explanation was written in Chinese
    monkeypatch.setattr(library, "user_examples", lambda: [chinese, malay])
    mine = [i for i in gp.build_pool("ms") if i.source == "yours"]
    # the Malay site shows only the Malay message (never the Chinese one), and explains it in Malay, not in the language the checker happened to be in
    assert [i.text[:8] for i in mine] == ["Pos Laju"] and "Syarikat sebenar" in mine[0].tell and "Berhenti" in mine[0].action
    zh = [i for i in gp.build_pool("zh") if i.source == "yours"]
    assert [i.text[:4] for i in zh] == ["【顺丰】"] and zh[0].tell == "正规公司会给你时间。"  # and the Chinese site shows the Chinese one, as written


FLAGGED = (V.SCAM, V.LIKELY_SCAM)


def verdict(text):
    return check_message(text, store=False, log=False).verdict


@pytest.mark.parametrize("ds", [ms_holdout, ms_fresh], ids=["holdout", "fresh"])
def test_rules_never_call_a_malay_scam_safe_and_never_flag_genuine_messages(ds):
    assert all(detect(t) == "ms" for _, t in ds.SCAMS + ds.LEGIT)
    safe = [i for i, t in ds.SCAMS if verdict(t) is V.SAFE]
    alarms = [i for i, t in ds.LEGIT if verdict(t) in FLAGGED]
    assert not safe, f"scams called safe: {safe}"
    assert not alarms, f"genuine messages flagged: {alarms}"


@pytest.mark.parametrize("ds", [ms_holdout, ms_fresh], ids=["holdout", "fresh"])
def test_rules_alone_catch_most_malay_scams(ds):
    caught = sum(verdict(t) in FLAGGED for _, t in ds.SCAMS)
    assert caught / len(ds.SCAMS) >= 0.85, f"{caught}/{len(ds.SCAMS)}"


@pytest.mark.parametrize("text", [
    "Kod TAC anda untuk log masuk ialah 774412. Jangan dedahkan kepada sesiapa, termasuk pegawai bank.",   # a warning not to share is not a request to share
    "Kode verifikasi Shopee Anda: 3921. Jangan beri kode ini ke siapa pun, termasuk pihak Shopee.",
    "Peringatan: bayaran insurans kereta anda akan tamat pada 15 November. Anda boleh perbaharui melalui aplikasi syarikat.",  # an insurance renewal is not an advance fee
    "Saya dah transfer RM300 untuk duit hadiah hari jadi adik, tolong semak ya.",                          # "dah" marks it as already done
])
def test_ordinary_malay_and_indonesian_notices_are_not_flagged(text):
    assert verdict(text) not in FLAGGED


def test_the_malay_twin_never_runs_on_english_or_chinese_text():
    d = Dual(r"\bpay\b", None, r"\bbayar\b|\btransfer\b")
    CURRENT.set("en")
    assert not d.search("please transfer the money") and not d.search("bayar sekarang")
    CURRENT.set("ms")
    assert d.search("sila transfer sekarang")
    CURRENT.set("en")
    # a full English check right after a Malay one must not inherit the Malay patterns
    verdict("Sila bayar yuran proses RM150 dahulu untuk menuntut hadiah anda.")
    assert verdict("Please be kind. Tahniah means congratulations in Malay.") is not V.SCAM


def test_a_typical_malay_scam_is_hard_evidence_when_it_asks_for_a_code_and_claims_to_be_the_bank():
    r = check_message("Kami dari bank anda. Ada transaksi mencurigakan RM5,600 ke luar negara. Untuk batalkan, sebut kod TAC yang baru anda terima.", store=False, log=False)
    assert r.verdict in FLAGGED and any(e.tactic == "otp-credential-phish" for e in r.evidence)


def test_an_indonesian_verification_code_notice_is_recognised_as_a_normal_login_code():
    r = check_message("Kode verifikasi Shopee Anda: 3921. Jangan beri kode ini ke siapa pun, termasuk pihak Shopee.", store=False, log=False)
    assert any(e.source == "purpose:one-time-code" and e.supports == "safe" for e in r.evidence)  # "verifikasi" here is the noun, not a request to verify


# ---------------------------------------------------------------- Indonesian: the pack, its language detection and the sets written to test it
from scripts import common  # noqa: E402
from tests.data.id import dev as id_dev, fresh as id_fresh, holdout as id_holdout  # noqa: E402


def _rules_only(text):
    with common.offline(net=True):
        v = check_message(text, store=False, log=False).verdict
    return "scam" if v in (V.SCAM, V.LIKELY_SCAM) else v.value


@pytest.mark.parametrize("ds,minimum", [(id_dev, 23), (id_holdout, 22), (id_fresh, 18)], ids=["dev", "holdout", "fresh"])
def test_the_rules_alone_catch_most_indonesian_scams_and_never_flag_an_ordinary_message(ds, minimum):
    caught = [tag for tag, text in ds.SCAMS if _rules_only(text) == "scam"]
    alarms = [tag for tag, text in ds.LEGIT if _rules_only(text) == "scam"]
    assert len(caught) >= minimum and not alarms, (len(caught), alarms)         # (measured 23/25, 24/25 and 19/20; the dev set was used to write the rules, the holdout was read once and then used, the fresh set once)


def test_every_indonesian_message_is_recognised_as_indonesian_and_no_english_one_is():
    from tests.data.en import hard_3, sg

    for ds in (id_dev, id_holdout, id_fresh):
        assert all(detect(t) == "ms" for _, t in ds.SCAMS + ds.LEGIT), [tag for tag, t in ds.SCAMS + ds.LEGIT if detect(t) != "ms"]
    assert not [tag for tag, t in hard_3.SCAMS + hard_3.LEGIT + sg.SCAMS + sg.LEGIT if detect(t) == "ms"]


def test_a_dont_share_warning_is_not_a_request_in_malay_and_indonesian():
    from core.pipelines.check import ingest, intent

    for text in ("Kod TAC anda untuk log masuk ialah 774412. Jangan dedahkan kepada sesiapa, termasuk pegawai bank.",
                 "Kode verifikasi Shopee Anda: 3921. Jangan beri kode ini ke siapa pun, termasuk pihak Shopee.",
                 "Kod OTP anda ialah 593021. Jangan kongsi dengan sesiapa. Sah selama 5 minit.",
                 "BCA: Waspada penipuan! BCA tidak pernah meminta PIN, password, atau kode OTP Anda melalui telepon, SMS, atau media sosial."):
        asks = intent._heuristic(ingest.ingest(text)).asks
        assert not asks & {"share_code", "share_credentials"}, text
    assert "share_code" in intent._heuristic(ingest.ingest("Mohon sebutkan kode OTP yang baru Anda terima kepada petugas kami.")).asks


def test_opening_hours_are_not_a_premium_rate_phone_number():
    from core.domain import privacy

    assert privacy.phones_in("Jadwal vaksin Rabu, 09.00-11.00. Mohon membawa buku KIA.") == [] and privacy.phones_in("Buka 8.30-17.30 setiap hari") == []
    assert privacy.phones_in("Hubungi 0812-3456-7890 sekarang") == ["081234567890"]


def test_a_courier_update_or_a_new_card_is_not_an_impersonation_and_an_apk_invitation_is():
    assert _rules_only("J&T Express: Paket Anda sedang diantar kurir hari ini. Mohon siapkan nomor HP untuk konfirmasi penerimaan. Resi JP1234567890.") != "scam"
    assert _rules_only("BNI: Kartu debit baru Anda telah dikirim ke alamat terdaftar. Aktivasi dilakukan di ATM BNI terdekat atau lewat aplikasi BNI Mobile.") != "scam"
    assert _rules_only("Assalamualaikum, kami mengundang Bapak/Ibu di acara pernikahan kami. Silakan lihat undangan digital di file Undangan_Pernikahan.apk") == "scam"
    assert _rules_only("Download the file Invoice_Update.apk to see your invoice and confirm the payment now.") != "safe"


def test_a_premium_sms_subscription_is_caught_in_indonesian_too():
    from core.pipelines.check.knowledge import PREMIUM_RE

    CURRENT.set("ms")
    assert PREMIUM_RE.search("Ketik REG HOKI kirim ke 9876 untuk hadiah") and PREMIUM_RE.search("Txt LOVE ADAM EVE 07123456789 ke 87077 150p")
    assert not PREMIUM_RE.search("Pembayaran Rp 100.000 berhasil")
