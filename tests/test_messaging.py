import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from app.services import messaging


def test_is_telegram_true_for_tg_prefixed_id():
    assert messaging.is_telegram("tg:12345") is True


def test_is_telegram_false_for_whatsapp_phone():
    assert messaging.is_telegram("491234567") is False


def test_send_text_routes_whatsapp_phone_to_evolution_api():
    with patch.object(messaging, "evolution_api") as mock_evo, \
         patch.object(messaging, "telegram_api") as mock_tg:
        messaging.send_text("491234567", "Hallo")

    mock_evo.send_text.assert_called_once_with("491234567", "Hallo")
    mock_tg.send_text.assert_not_called()


def test_send_text_routes_telegram_id_to_telegram_api_with_prefix_stripped():
    with patch.object(messaging, "evolution_api") as mock_evo, \
         patch.object(messaging, "telegram_api") as mock_tg:
        messaging.send_text("tg:12345", "Hallo")

    mock_tg.send_text.assert_called_once_with("12345", "Hallo")
    mock_evo.send_text.assert_not_called()


def test_send_document_routes_whatsapp_phone_to_evolution_api():
    with patch.object(messaging, "evolution_api") as mock_evo, \
         patch.object(messaging, "telegram_api") as mock_tg:
        messaging.send_document("491234567", "/tmp/report.pdf", "report.pdf", caption="Hi")

    mock_evo.send_document.assert_called_once_with("491234567", "/tmp/report.pdf", "report.pdf", "Hi")
    mock_tg.send_document.assert_not_called()


def test_send_document_routes_telegram_id_to_telegram_api_with_prefix_stripped():
    with patch.object(messaging, "evolution_api") as mock_evo, \
         patch.object(messaging, "telegram_api") as mock_tg:
        messaging.send_document("tg:12345", "/tmp/report.pdf", "report.pdf", caption="Hi")

    mock_tg.send_document.assert_called_once_with("12345", "/tmp/report.pdf", "report.pdf", "Hi")
    mock_evo.send_document.assert_not_called()
