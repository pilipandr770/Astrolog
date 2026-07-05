import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from dataclasses import dataclass
from datetime import date, datetime
from unittest.mock import patch

from app.config import Config
from app.services import dialog_manager
from app.services.dialog_manager import (
    _capture_language_signal,
    _handle_post_report_chat,
    _handle_sales_chat,
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


def test_handle_sales_chat_stays_in_chat_when_not_ready():
    with patch.object(dialog_manager, "evolution_api") as mock_evo, \
         patch.object(dialog_manager, "conversation_state") as mock_state, \
         patch.object(dialog_manager.claude_service, "generate_sales_reply") as mock_reply:
        mock_reply.return_value = ("Klar, erzähl mir gern, was dich interessiert!", False)
        _handle_sales_chat("491234567", "Was kostet das denn?", {})

    mock_state.update.assert_called_once()
    call_kwargs = mock_state.update.call_args
    assert call_kwargs[0][0] == "491234567"
    assert call_kwargs[1]["state"] == "sales_chat"
    saved_history = json.loads(call_kwargs[1]["sales_chat_history"])
    assert saved_history == [
        {"role": "user", "content": "Was kostet das denn?"},
        {"role": "assistant", "content": "Klar, erzähl mir gern, was dich interessiert!"},
    ]
    mock_evo.send_text.assert_called_once_with(
        "491234567", "Klar, erzähl mir gern, was dich interessiert!"
    )


def test_handle_sales_chat_transitions_to_awaiting_date_when_ready():
    with patch.object(dialog_manager, "evolution_api") as mock_evo, \
         patch.object(dialog_manager, "conversation_state") as mock_state, \
         patch.object(dialog_manager.claude_service, "generate_sales_reply") as mock_reply:
        mock_reply.return_value = ("Super, dann leg los!", True)
        _handle_sales_chat("491234567", "Ja, lass uns anfangen", {})

    mock_state.update.assert_called_once_with(
        "491234567", state="awaiting_date", sales_chat_history=None
    )
    assert mock_evo.send_text.call_count == 2
    assert mock_evo.send_text.call_args_list[0][0][1] == "Super, dann leg los!"
    assert "Geburtsdatum" in mock_evo.send_text.call_args_list[1][0][1]


def test_handle_sales_chat_passes_existing_history_and_caps_length():
    long_history = [{"role": "user", "content": f"msg{i}"} for i in range(30)]
    state = {"sales_chat_history": json.dumps(long_history)}

    with patch.object(dialog_manager, "evolution_api"), \
         patch.object(dialog_manager, "conversation_state") as mock_state, \
         patch.object(dialog_manager.claude_service, "generate_sales_reply") as mock_reply:
        mock_reply.return_value = ("Antwort", False)
        _handle_sales_chat("491234567", "weiter", state)

    assert mock_reply.call_args[0][1] == long_history
    saved_history = json.loads(mock_state.update.call_args[1]["sales_chat_history"])
    assert len(saved_history) <= dialog_manager.MAX_SALES_HISTORY_TURNS * 2


def test_handle_sales_chat_handles_claude_error_gracefully():
    with patch.object(dialog_manager, "evolution_api") as mock_evo, \
         patch.object(dialog_manager, "conversation_state") as mock_state, \
         patch.object(dialog_manager.claude_service, "generate_sales_reply", side_effect=RuntimeError("boom")):
        _handle_sales_chat("491234567", "Hallo", {})

    mock_state.update.assert_not_called()
    mock_evo.send_text.assert_called_once()


def test_handle_post_report_chat_uses_stored_interpretation_and_saves_history():
    state = {
        "last_interpretation": "Dein Mond steht im 4. Haus...",
        "post_report_chat_history": None,
        "report_calendar_end_date": "2026-08-02",
    }

    fake_now = datetime(2026, 7, 5, 14, 32, tzinfo=dialog_manager.BERLIN_TZ)
    fake_snapshot = {"date": date(2026, 7, 5), "blocks": []}
    with patch.object(dialog_manager, "evolution_api") as mock_evo, \
         patch.object(dialog_manager, "conversation_state") as mock_state, \
         patch.object(dialog_manager, "_now_in_berlin", return_value=fake_now), \
         patch.object(dialog_manager.report_generator, "compute_today_snapshot", return_value=fake_snapshot) as mock_snap, \
         patch.object(dialog_manager.claude_service, "generate_post_report_reply") as mock_reply:
        mock_reply.return_value = ("Das bedeutet, dass...", False)
        _handle_post_report_chat("491234567", "Was bedeutet mein Mondhaus?", state)

    mock_snap.assert_called_once_with(state, target_date=date(2026, 7, 5))
    mock_reply.assert_called_once_with(
        state, "Dein Mond steht im 4. Haus...", [], "Was bedeutet mein Mondhaus?",
        calendar_end_date="2026-08-02", now_str="05.07.2026 14:32 Uhr (Europe/Berlin)",
        today_snapshot=fake_snapshot,
    )
    mock_evo.send_text.assert_called_once_with("491234567", "Das bedeutet, dass...")
    saved_history = json.loads(mock_state.update.call_args[1]["post_report_chat_history"])
    assert saved_history == [
        {"role": "user", "content": "Was bedeutet mein Mondhaus?"},
        {"role": "assistant", "content": "Das bedeutet, dass..."},
    ]


def test_handle_post_report_chat_falls_back_without_stored_report():
    state = {}

    with patch.object(dialog_manager, "evolution_api"), \
         patch.object(dialog_manager, "conversation_state"), \
         patch.object(dialog_manager.report_generator, "compute_today_snapshot", return_value=None), \
         patch.object(dialog_manager.claude_service, "generate_post_report_reply") as mock_reply:
        mock_reply.return_value = ("Antwort", False)
        _handle_post_report_chat("491234567", "Frage", state)

    assert "Kein gespeicherter Berichtstext" in mock_reply.call_args[0][1]


def test_handle_post_report_chat_handles_claude_error_gracefully():
    with patch.object(dialog_manager, "evolution_api") as mock_evo, \
         patch.object(dialog_manager, "conversation_state") as mock_state, \
         patch.object(dialog_manager.report_generator, "compute_today_snapshot", return_value=None), \
         patch.object(dialog_manager.claude_service, "generate_post_report_reply", side_effect=RuntimeError("boom")):
        _handle_post_report_chat("491234567", "Frage", {})

    mock_state.update.assert_not_called()
    mock_evo.send_text.assert_called_once()


def test_handle_post_report_chat_triggers_renewal_when_customer_agrees():
    state = {
        "birth_date": "1990-05-15", "birth_time": "14:30", "birth_place": "Berlin",
        "last_interpretation": "Bericht-Text", "post_report_chat_history": None,
    }

    with patch.object(dialog_manager, "evolution_api") as mock_evo, \
         patch.object(dialog_manager, "conversation_state") as mock_state, \
         patch.object(dialog_manager.report_generator, "compute_today_snapshot", return_value=None), \
         patch.object(dialog_manager.claude_service, "generate_post_report_reply") as mock_reply, \
         patch.object(dialog_manager, "_send_payment_link") as mock_payment:
        mock_reply.return_value = ("Perfekt, ich erstelle dir die Fortsetzung!", True)
        mock_state.get_or_create.return_value = state
        _handle_post_report_chat("491234567", "Ja, mach das bitte", state)

    mock_evo.send_text.assert_called_once_with(
        "491234567", "Perfekt, ich erstelle dir die Fortsetzung!"
    )
    mock_state.update.assert_called_once_with(
        "491234567",
        state="awaiting_payment",
        paid=0,
        stripe_session_id=None,
        last_interpretation=None,
        post_report_chat_history=None,
        report_calendar_end_date=None,
    )
    mock_payment.assert_called_once_with("491234567", state, with_summary=True)


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
