import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

from app.services import telegram_api


def test_send_text_sends_single_message_for_short_text():
    with patch.object(telegram_api.requests, "post") as mock_post:
        mock_post.return_value = MagicMock(json=lambda: {"ok": True})
        result = telegram_api.send_text("12345", "Kurze Nachricht")

    assert len(result) == 1
    mock_post.assert_called_once()
    sent_payload = mock_post.call_args.kwargs["json"]
    assert sent_payload == {"chat_id": "12345", "text": "Kurze Nachricht"}


def test_send_text_sends_multiple_sequential_messages_for_long_text():
    long_text = ("Das ist ein langer Absatz mit vielen Woertern. " * 200) + "\n\n" + (
        "Und noch ein zweiter Absatz. " * 200
    )

    with patch.object(telegram_api.requests, "post") as mock_post:
        mock_post.return_value = MagicMock(json=lambda: {"ok": True})
        result = telegram_api.send_text("12345", long_text)

    assert len(result) > 1
    assert mock_post.call_count == len(result)
    for call in mock_post.call_args_list:
        assert len(call.kwargs["json"]["text"]) <= telegram_api.MAX_TEXT_LENGTH
        assert call.kwargs["json"]["chat_id"] == "12345"


def test_send_document_posts_multipart_with_chat_id_and_caption(tmp_path):
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake content")

    with patch.object(telegram_api.requests, "post") as mock_post:
        mock_post.return_value = MagicMock(json=lambda: {"ok": True})
        telegram_api.send_document("12345", str(pdf_path), "report.pdf", caption="Hier ist dein Bericht")

    mock_post.assert_called_once()
    sent_data = mock_post.call_args.kwargs["data"]
    assert sent_data == {"chat_id": "12345", "caption": "Hier ist dein Bericht"}
    assert "document" in mock_post.call_args.kwargs["files"]


def test_get_file_download_url_builds_url_from_file_path():
    with patch.object(telegram_api.requests, "get") as mock_get:
        mock_get.return_value = MagicMock(
            json=lambda: {"result": {"file_path": "voice/file_1.oga"}}
        )
        url = telegram_api.get_file_download_url("TGFILE123")

    assert url == f"{telegram_api.FILE_BASE_URL}/voice/file_1.oga"
    mock_get.assert_called_once()
    assert mock_get.call_args.kwargs["params"] == {"file_id": "TGFILE123"}


def _update(message):
    return {"update_id": 1, "message": message}


def test_extract_incoming_message_parses_text():
    payload = _update({
        "message_id": 42, "date": 1234567890,
        "chat": {"id": 987654321}, "text": "Hallo!",
    })
    result = telegram_api.extract_incoming_message(payload)
    assert result == {
        "phone": "tg:987654321", "type": "text", "content": "Hallo!",
        "message_id": 42, "timestamp": 1234567890,
    }


def test_extract_incoming_message_parses_voice():
    payload = _update({
        "message_id": 43, "date": 1234567890,
        "chat": {"id": 987654321}, "voice": {"file_id": "TGFILE123", "duration": 5},
    })
    result = telegram_api.extract_incoming_message(payload)
    assert result == {
        "phone": "tg:987654321", "type": "audio", "file_id": "TGFILE123",
        "message_id": 43, "timestamp": 1234567890,
    }


def test_extract_incoming_message_returns_none_for_unknown_type():
    payload = _update({
        "message_id": 44, "date": 1234567890,
        "chat": {"id": 987654321}, "sticker": {"file_id": "STICKER1"},
    })
    assert telegram_api.extract_incoming_message(payload) is None


def test_extract_incoming_message_handles_malformed_payload_gracefully():
    assert telegram_api.extract_incoming_message({}) is None
    assert telegram_api.extract_incoming_message({"update_id": 1}) is None


def test_extract_incoming_message_falls_back_to_edited_message():
    payload = {
        "update_id": 1,
        "edited_message": {
            "message_id": 45, "date": 1234567890,
            "chat": {"id": 987654321}, "text": "Korrigiert",
        },
    }
    result = telegram_api.extract_incoming_message(payload)
    assert result["content"] == "Korrigiert"


def test_set_webhook_posts_url():
    with patch.object(telegram_api.requests, "post") as mock_post:
        mock_post.return_value = MagicMock(json=lambda: {"ok": True, "result": True})
        result = telegram_api.set_webhook("https://example.com/webhook/telegram")

    assert result == {"ok": True, "result": True}
    mock_post.assert_called_once()
    assert mock_post.call_args.kwargs["json"] == {"url": "https://example.com/webhook/telegram"}
