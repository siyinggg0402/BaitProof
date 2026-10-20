from core.domain.schemas import Verdict as V
from core.pipelines.check import check_message
from tests.data.en import heldout_1, heldout_2


def _verdicts(items):
    return [check_message(t if isinstance(t, str) else t[0], store=False).verdict for t in items]


def test_heldout1_no_false_safe_on_scams():
    missed = [t[1] + ": " + t[0][:50] for t, v in zip(heldout_1.SCAMS, _verdicts(heldout_1.SCAMS)) if v == V.SAFE]
    assert not missed, missed


def test_heldout1_scam_recall():
    flagged = sum(v in (V.SCAM, V.LIKELY_SCAM) for v in _verdicts(heldout_1.SCAMS))
    assert flagged / len(heldout_1.SCAMS) >= 0.85, flagged


def test_heldout1_no_false_alarms_on_legit():
    bad = [t[:50] for t, v in zip(heldout_1.LEGIT, _verdicts(heldout_1.LEGIT)) if v in (V.SCAM, V.LIKELY_SCAM)]
    assert not bad, bad


def test_heldout2_no_false_safe_and_no_false_alarms():
    missed = [tag for t, tag in heldout_2.SCAMS if check_message(t, store=False).verdict == V.SAFE]
    alarms = [t[:40] for t in heldout_2.LEGIT if check_message(t, store=False).verdict in (V.SCAM, V.LIKELY_SCAM)]
    assert not missed and not alarms, (missed, alarms)
