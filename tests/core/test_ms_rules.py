"""Malay and Indonesian rules (no model). The two sets are authored (see their docstrings): ms_holdout was a first reading, ms_fresh was written after
the rules existed and was then used to fix the gaps it exposed, so both now count as development sets."""
import pytest

from core.domain.lang import CURRENT, Dual, detect
from core.domain.schemas import Verdict as V
from core.pipelines.check import check_message
from tests.data import ms_fresh, ms_holdout

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
