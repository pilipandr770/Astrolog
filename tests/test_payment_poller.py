import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from app.services import payment_poller


def _fake_convo(phone="491234567", session_id="cs_test_123"):
    return {"phone": phone, "state": "awaiting_payment", "stripe_session_id": session_id}


def test_check_pending_payments_marks_paid_notifies_and_generates_report():
    with patch(
        "app.services.payment_poller.conversation_state.find_awaiting_payment",
        return_value=[_fake_convo()],
    ), patch(
        "app.services.payment_poller.stripe_service.get_payment_status",
        return_value="paid",
    ), patch(
        "app.services.payment_poller.conversation_state.update"
    ) as mock_update, patch(
        "app.services.payment_poller.messaging.send_text"
    ) as mock_send, patch(
        "app.services.payment_poller.report_generator.generate_and_send_report"
    ) as mock_report:
        payment_poller.check_pending_payments()

    mock_update.assert_called_once_with("491234567", paid=1, state="paid")
    mock_send.assert_called_once()
    assert "491234567" == mock_send.call_args[0][0]
    mock_report.assert_called_once_with("491234567")


def test_check_pending_payments_skips_unpaid():
    with patch(
        "app.services.payment_poller.conversation_state.find_awaiting_payment",
        return_value=[_fake_convo()],
    ), patch(
        "app.services.payment_poller.stripe_service.get_payment_status",
        return_value="unpaid",
    ), patch(
        "app.services.payment_poller.conversation_state.update"
    ) as mock_update, patch(
        "app.services.payment_poller.messaging.send_text"
    ) as mock_send:
        payment_poller.check_pending_payments()

    mock_update.assert_not_called()
    mock_send.assert_not_called()


def test_check_pending_payments_handles_stripe_error_gracefully():
    with patch(
        "app.services.payment_poller.conversation_state.find_awaiting_payment",
        return_value=[_fake_convo()],
    ), patch(
        "app.services.payment_poller.stripe_service.get_payment_status",
        side_effect=RuntimeError("Stripe API down"),
    ), patch(
        "app.services.payment_poller.conversation_state.update"
    ) as mock_update, patch(
        "app.services.payment_poller.messaging.send_text"
    ) as mock_send:
        payment_poller.check_pending_payments()  # muss NICHT crashen

    mock_update.assert_not_called()
    mock_send.assert_not_called()


def test_check_pending_payments_processes_multiple_conversations():
    convos = [_fake_convo("491111111", "cs_a"), _fake_convo("492222222", "cs_b")]
    with patch(
        "app.services.payment_poller.conversation_state.find_awaiting_payment",
        return_value=convos,
    ), patch(
        "app.services.payment_poller.stripe_service.get_payment_status",
        side_effect=["paid", "unpaid"],
    ), patch(
        "app.services.payment_poller.conversation_state.update"
    ) as mock_update, patch(
        "app.services.payment_poller.messaging.send_text"
    ) as mock_send, patch(
        "app.services.payment_poller.report_generator.generate_and_send_report"
    ) as mock_report:
        payment_poller.check_pending_payments()

    mock_update.assert_called_once_with("491111111", paid=1, state="paid")
    mock_send.assert_called_once()
    mock_report.assert_called_once_with("491111111")
