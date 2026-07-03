import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

from app.services import whisper_service


def test_transcribe_from_url_returns_text_and_detected_language():
    fake_transcript = MagicMock(text="Hallo Welt", language="german")

    with patch("app.services.whisper_service.requests.get") as mock_get, \
         patch.object(whisper_service, "_get_client") as mock_get_client:
        mock_get.return_value.content = b"fake-audio-bytes"
        mock_get.return_value.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = fake_transcript
        mock_get_client.return_value = mock_client

        result = whisper_service.transcribe_from_url("https://example.com/voice.ogg")

    assert result == {"text": "Hallo Welt", "language": "german"}
    # Kein hartkodiertes language= an die API übergeben — Whisper soll selbst erkennen.
    call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
    assert "language" not in call_kwargs
    assert call_kwargs["response_format"] == "verbose_json"


def test_transcribe_from_url_handles_missing_language_field():
    fake_transcript = MagicMock(spec=["text"], text="Hi")  # kein .language-Attribut

    with patch("app.services.whisper_service.requests.get") as mock_get, \
         patch.object(whisper_service, "_get_client") as mock_get_client:
        mock_get.return_value.content = b"fake-audio-bytes"
        mock_get.return_value.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = fake_transcript
        mock_get_client.return_value = mock_client

        result = whisper_service.transcribe_from_url("https://example.com/voice.ogg")

    assert result == {"text": "Hi", "language": None}
