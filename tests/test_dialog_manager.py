import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dataclasses import dataclass
from unittest.mock import patch

from app.config import Config
from app.services import dialog_manager
from app.services.dialog_manager import (
    _capture_language_signal,
    _handle_style,
    _payment_redirect_urls,
    _pick_teaser_findings,
    _style_menu_text,
)


@dataclass
class _FakeFinding:
    planet: str
    house: int


def test_payment_redirect_urls_use_wame_by_default(monkeypatch):
    monkeypatch.setattr(Config, "APP_BASE_URL", "")
    monkeypatch.setattr(Config, "BOT_WHATSAPP_NUMBER", "4915123456789")

    success_url, cancel_url = _payment_redirect_urls()

    assert success_url.startswith("https://wa.me/4915123456789")
    assert cancel_url.startswith("https://wa.me/4915123456789")
    assert success_url != cancel_url


def test_payment_redirect_urls_prefer_app_base_url_if_set(monkeypatch):
    monkeypatch.setattr(Config, "APP_BASE_URL", "https://my-domain.example")
    monkeypatch.setattr(Config, "BOT_WHATSAPP_NUMBER", "4915123456789")

    success_url, cancel_url = _payment_redirect_urls()

    assert success_url.startswith("https://my-domain.example/payment/success")
    assert cancel_url == "https://my-domain.example/payment/cancel"


def test_pick_teaser_findings_prefers_moon_and_sun():
    findings = [
        _FakeFinding("Saturn", 10),
        _FakeFinding("Moon", 6),
        _FakeFinding("Sun", 1),
        _FakeFinding("Mars", 3),
    ]
    picks = _pick_teaser_findings(findings)
    assert [f.planet for f in picks] == ["Moon", "Sun"]


def test_pick_teaser_findings_falls_back_to_jupiter_without_sun():
    findings = [_FakeFinding("Moon", 6), _FakeFinding("Jupiter", 9), _FakeFinding("Mars", 3)]
    picks = _pick_teaser_findings(findings)
    assert [f.planet for f in picks] == ["Moon", "Jupiter"]


def test_pick_teaser_findings_returns_at_most_two():
    findings = [_FakeFinding("Moon", 6), _FakeFinding("Sun", 1), _FakeFinding("Jupiter", 9)]
    picks = _pick_teaser_findings(findings)
    assert len(picks) == 2


def test_pick_teaser_findings_handles_missing_moon():
    findings = [_FakeFinding("Sun", 1), _FakeFinding("Mars", 3)]
    picks = _pick_teaser_findings(findings)
    assert [f.planet for f in picks] == ["Sun"]


def test_pick_teaser_findings_empty_input():
    assert _pick_teaser_findings([]) == []


def test_capture_language_signal_stores_first_sample():
    with patch.object(dialog_manager.conversation_state, "update") as mock_update:
        _capture_language_signal("491234567", {}, "Hello, I need a horoscope")
    mock_update.assert_called_once_with(
        "491234567", language_sample="Hello, I need a horoscope"
    )


def test_capture_language_signal_skips_if_hint_already_present():
    with patch.object(dialog_manager.conversation_state, "update") as mock_update:
        _capture_language_signal("491234567", {"language_hint": "english"}, "Bonjour")
    mock_update.assert_not_called()


def test_capture_language_signal_skips_if_sample_already_present():
    with patch.object(dialog_manager.conversation_state, "update") as mock_update:
        _capture_language_signal("491234567", {"language_sample": "Hi"}, "Bonjour")
    mock_update.assert_not_called()


def test_capture_language_signal_ignores_blank_text():
    with patch.object(dialog_manager.conversation_state, "update") as mock_update:
        _capture_language_signal("491234567", {}, "   ")
    mock_update.assert_not_called()


def test_handle_style_reprompts_on_invalid_input():
    with patch.object(dialog_manager, "evolution_api") as mock_evo, \
         patch.object(dialog_manager, "conversation_state") as mock_state:
        _handle_style("491234567", "keine Ahnung", {})
    mock_state.update.assert_not_called()
    sent_text = mock_evo.send_text.call_args[0][1]
    assert "1 bis 4" in sent_text


def test_handle_style_accepts_valid_digit_and_proceeds():
    fake_state = {"birth_date": "1990-05-15", "birth_time": "14:30", "birth_place": "Berlin"}
    with patch.object(dialog_manager, "conversation_state") as mock_state, \
         patch.object(dialog_manager, "_send_teaser") as mock_teaser, \
         patch.object(dialog_manager, "_send_payment_link") as mock_payment:
        mock_state.get_or_create.return_value = fake_state
        _handle_style("491234567", "2", {})

    mock_state.update.assert_called_once_with("491234567", style="humorous", state="awaiting_payment")
    mock_teaser.assert_called_once()
    mock_payment.assert_called_once()


def test_extract_text_audio_uses_evolution_base64_not_encrypted_url():
    # Die Webhook-URL (mmg.whatsapp.net/...enc) ist E2E-verschlüsselt —
    # das Audio MUSS über get_media_base64 von Evolution geholt werden.
    message = {
        "type": "audio",
        "media_url": "https://mmg.whatsapp.net/xyz.enc",
        "message_key": {"id": "MSG123", "remoteJid": "491234567@s.whatsapp.net"},
    }
    with patch.object(dialog_manager, "evolution_api") as mock_evo, \
         patch.object(dialog_manager, "whisper_service") as mock_whisper, \
         patch.object(dialog_manager.conversation_state, "update") as mock_update:
        mock_evo.get_media_base64.return_value = {
            "base64": "AAAA",
            "mimetype": "audio/ogg; codecs=opus",
        }
        mock_whisper.transcribe_from_base64.return_value = {
            "text": "15.05.1990",
            "language": "german",
        }
        text = dialog_manager._extract_text("491234567", message)

    assert text == "15.05.1990"
    mock_evo.get_media_base64.assert_called_once_with(message["message_key"])
    mock_whisper.transcribe_from_base64.assert_called_once_with(
        "AAAA", "audio/ogg; codecs=opus"
    )
    mock_whisper.transcribe_from_url.assert_not_called()
    mock_update.assert_called_once_with("491234567", language_hint="german")


def test_style_menu_text_extracts_digit_anywhere_in_message():
    # "_handle_style" sucht die erste Ziffer 1-4 irgendwo im Text (z.B. "3." oder "Nummer 3")
    with patch.object(dialog_manager, "conversation_state") as mock_state, \
         patch.object(dialog_manager, "_send_teaser"), \
         patch.object(dialog_manager, "_send_payment_link"):
        mock_state.get_or_create.return_value = {}
        _handle_style("491234567", "Nummer 3 bitte", {})
    mock_state.update.assert_called_once_with("491234567", style="business", state="awaiting_payment")
