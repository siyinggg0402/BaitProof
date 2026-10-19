import pytest

from core.domain.schemas import Verdict as V
from core.pipelines.check import check_message
from tests import heldout


def _verdicts(items):
    return [check_message(t if isinstance(t, str) else t[0], store=False).verdict for t in items]


def test_heldout_no_false_safe_on_scams():
    missed = [t[1] + ": " + t[0][:50] for t, v in zip(heldout.SCAMS, _verdicts(heldout.SCAMS)) if v == V.SAFE]
    assert not missed, missed


def test_heldout_scam_recall():
    flagged = sum(v in (V.SCAM, V.LIKELY_SCAM) for v in _verdicts(heldout.SCAMS))
    assert flagged / len(heldout.SCAMS) >= 0.85, flagged


def test_heldout_no_false_alarms_on_legit():
    bad = [t[:50] for t, v in zip(heldout.LEGIT, _verdicts(heldout.LEGIT)) if v in (V.SCAM, V.LIKELY_SCAM)]
    assert not bad, bad
