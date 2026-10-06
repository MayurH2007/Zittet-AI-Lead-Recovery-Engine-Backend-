"""Opt-out detection tests."""

from __future__ import annotations

from app.utils.opt_out import any_customer_opted_out, contains_opt_out_signal


def test_stop_detected():
    assert contains_opt_out_signal("STOP") is True


def test_dont_message_me_again_detected():
    assert contains_opt_out_signal("Don't message me again.") is True


def test_unsubscribe_detected():
    assert contains_opt_out_signal("Please unsubscribe me") is True


def test_opt_out_detected():
    assert contains_opt_out_signal("I want to opt out") is True


def test_remove_me_detected():
    assert contains_opt_out_signal("remove me from your list") is True


def test_no_opt_out_signal():
    assert contains_opt_out_signal("I am interested in pricing") is False
    assert contains_opt_out_signal("") is False


def test_any_customer_opted_out_true():
    msgs = [("customer", "STOP"), ("agent", "ok")]
    assert any_customer_opted_out(msgs) is True


def test_any_customer_opted_out_only_agent_message_ignored():
    msgs = [("agent", "STOP sending messages")]
    assert any_customer_opted_out(msgs) is False


def test_any_customer_opted_out_false():
    msgs = [("customer", "what is the price?")]
    assert any_customer_opted_out(msgs) is False
