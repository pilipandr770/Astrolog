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


def test_transcribe_from_base64_decodes_and_names_file_by_mimetype():
    import base64 as b64mod

    fake_transcript = MagicMock(text="Hallo", language="german")
    encoded = b64mod.b64encode(b"fake-decrypted-audio").decode()

    with patch.object(whisper_service, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = fake_transcript
        mock_get_client.return_value = mock_client

        result = whisper_service.transcribe_from_base64(
            encoded, "audio/ogg; codecs=opus"
        )

    assert result == {"text": "Hallo", "language": "german"}
    sent_file = mock_client.audio.transcriptions.create.call_args.kwargs["file"]
    assert sent_file.name == "voice.ogg"
    assert sent_file.getvalue() == b"fake-decrypted-audio"


def test_ext_from_mimetype_variants():
    assert whisper_service._ext_from_mimetype("audio/ogg; codecs=opus") == "ogg"
    assert whisper_service._ext_from_mimetype("audio/mp4") == "m4a"
    assert whisper_service._ext_from_mimetype("audio/mpeg") == "mp3"
    assert whisper_service._ext_from_mimetype(None) == "ogg"
    assert whisper_service._ext_from_mimetype("application/unknown") == "ogg"
