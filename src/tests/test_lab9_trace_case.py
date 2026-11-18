"""Regression test from docs/trace_case.md: C-002@11, FM-03 ticket_trust.

The first wrong step is the `model_override` event that replaces the DB's delay_days=2
with the ticket's 5. It must show up on seeded_regression and never on fixed.
"""

import pytest

from lab9.trace_case import investigate

pytestmark = pytest.mark.student


def _kinds(trial):
    return [e.get("kind") for e in trial["events"]]


def test_c002_ticket_trust_is_caught_on_seeded_regression():
    case = investigate("seeded_regression", "C-002", 11)
    t, label = case["trial"], case["label"]
    kinds = _kinds(t)
    assert "model_override" in kinds
    first_bad = kinds.index("model_override")
    db_delay = t["events"][first_bad - 1]["payload"]["lookup_order"]["order"]["delay_days"]
    assert db_delay == 2 and t["events"][first_bad]["payload"] == {"delay_days": 5}
    assert t["snapshot"]["refund_vnd"] != label["refund_vnd"]   # ledger 20.000, label 0
    assert not t["lab8_pass"]


def test_c002_fixed_keeps_the_db_fact():
    case = investigate("fixed", "C-002", 11)
    t, label = case["trial"], case["label"]
    assert "model_override" not in _kinds(t)
    assert t["snapshot"]["refund_vnd"] == label["refund_vnd"] == 0
    assert t["result"]["status"] == label["status"] == "denied"
    assert t["lab8_pass"]
