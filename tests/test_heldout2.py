from core.domain.schemas import Verdict as V
from core.pipelines.check import check_message
from tests import heldout2


def test_set2_no_false_safe_and_no_false_alarms():
    missed = [tag for t, tag in heldout2.SCAMS if check_message(t, store=False).verdict == V.SAFE]
    alarms = [t[:40] for t in heldout2.LEGIT if check_message(t, store=False).verdict in (V.SCAM, V.LIKELY_SCAM)]
    assert not missed and not alarms, (missed, alarms)
