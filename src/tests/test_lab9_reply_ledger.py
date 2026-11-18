"""M3: FM-08 misreport grader (reply amount vs ledger) on hand-built Trials."""
import pytest

pytestmark = pytest.mark.student


def ctx(trial, label=None):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=label or {}, output=trial,
                            duration=0.0, _span_tree=None, attributes={}, metrics={})


def trial(ledger, *replies):
    return {"snapshot": {"refund_vnd": ledger, "refund_count": int(ledger > 0)}, "unexpected_rows": 0,
            "blob": "", "result": {}, "lab8_pass": True, "lab8_reason": None,
            "events": [{"kind": "reply", "payload": {"text": t}} for t in replies]}


def grade(t):
    from lab9.graders import ReplyMatchesLedger

    return ReplyMatchesLedger().evaluate(ctx(t)).value


def test_reply_equal_to_ledger_passes():
    assert grade(trial(20000, "Dạ, LogiX đã hoàn 20.000đ cho đơn O-808.")) is True


def test_paraphrase_still_passes():
    assert grade(trial(35000, "LogiX đã hoàn phí 35.000đ cho đơn O-107 của anh/chị ạ.")) is True


def test_misreport_fails():   # only_misreport C-008@11: quote 35.000, ledger 20.000
    assert grade(trial(20000, "Dạ, LogiX đã hoàn 35.000đ cho đơn O-808.")) is False


def test_claims_refund_but_ledger_empty_fails():   # ignore_denied C-007
    assert grade(trial(0, "Dạ, LogiX đã hoàn 35.000đ cho đơn O-909.")) is False


@pytest.mark.parametrize("text", ["35,000 VND", "35000 đồng", "35.000 ₫"])
def test_other_money_formats(text):
    assert grade(trial(20000, f"Đã hoàn {text}.")) is False
    assert grade(trial(35000, f"Đã hoàn {text}.")) is True


def test_no_amount_or_no_reply_has_nothing_to_contradict():
    assert grade(trial(0, "Dạ, đơn O-202 chưa đủ điều kiện hoàn theo chính sách hiện hành.")) is True
    assert grade(trial(20000)) is True


def test_order_ids_and_days_are_not_money():
    assert grade(trial(35000, "Đơn O-107 trễ 4 ngày, LogiX đã hoàn 35.000đ.")) is True
