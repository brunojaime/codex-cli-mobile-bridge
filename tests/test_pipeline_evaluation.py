import pytest

from scripts.jev_lab.evaluate_pipeline import evaluate
from scripts.sync_pipeline_gestion import sync


def test_pairing_and_failures_are_not_dropped():
    rows = [
        {
            "case_id": "one",
            "repeat": 1,
            "arm": arm,
            "accepted": arm != "C",
            "elapsed_ms": 100,
            "human_minutes": 1,
            "cost_usd": 0.1,
            "false_closure": False,
        }
        for arm in "ABC"
    ]
    result = evaluate(rows)
    assert result["arms"]["C"]["runs"] == 1 and result["arms"]["C"]["accepted"] == 0
    assert result["verdict"] == "inconclusive"
    with pytest.raises(ValueError, match="All A/B/C"):
        evaluate(rows[:2])
    rows[2]["false_closure"] = True
    assert evaluate(rows)["verdict"] == "stop_false_closure"


@pytest.mark.parametrize(
    "origin",
    [
        "https://gestion.nienfos.com",
        "https://dev.gestion.nienfos.com.evil.test",
        "http://example.test",
        "https://user:password@dev.gestion.nienfos.com",
    ],
)
def test_sync_rejects_wrong_origins_before_network(origin):
    with pytest.raises(ValueError):
        sync({}, origin=origin, token="local-test-only")
