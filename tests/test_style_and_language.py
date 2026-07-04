import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from app.services import claude_service
from app.services.dialog_manager import _style_menu_text, _STYLE_ORDER


def test_get_style_instruction_known_key():
    instruction = claude_service.get_style_instruction("humorous")
    assert "umorvoll" in instruction or "ocker" in instruction


def test_get_style_instruction_unknown_key_falls_back_to_default():
    default_instruction = claude_service.get_style_instruction(claude_service.DEFAULT_STYLE_KEY)
    assert claude_service.get_style_instruction("does-not-exist") == default_instruction
    assert claude_service.get_style_instruction(None) == default_instruction


def test_language_directive_prefers_whisper_hint_over_sample():
    directive = claude_service._language_directive({"language_hint": "english", "language_sample": "Hallo"})
    assert "english" in directive


def test_language_directive_uses_sample_when_no_hint():
    directive = claude_service._language_directive({"language_sample": "Hello there"})
    assert "Hello there" in directive


def test_language_directive_defaults_to_german_without_signal():
    directive = claude_service._language_directive({})
    assert "Deutsch" in directive


def test_style_menu_text_lists_all_presets_in_order():
    menu = _style_menu_text()
    for number, key in enumerate(_STYLE_ORDER, start=1):
        label = claude_service.STYLE_PRESETS[key]["label"]
        assert f"{number}️⃣ {label}" in menu
    assert "(Standard)" in menu


def test_generate_interpretation_includes_style_and_language(monkeypatch):
    fake_block = type("Block", (), {"type": "text", "text": "Auswertung"})()
    fake_response = type("Response", (), {"content": [fake_block]})()

    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return fake_response

    with patch.object(claude_service.settings, "get_setting", return_value=""), \
         patch.object(claude_service.client.messages, "create", side_effect=fake_create):
        claude_service.generate_interpretation(
            {"style": "business", "language_sample": "Bonjour"},
            {"Moon": {"sign": "Cancer", "house": 6}},
            [],
        )

    user_message = captured["messages"][0]["content"]
    assert "business" in user_message.lower() or "sachlich" in user_message.lower()
    assert "Bonjour" in user_message


def test_generate_interpretation_includes_calendar_highlights():
    from datetime import date

    fake_block = type("Block", (), {"type": "text", "text": "Auswertung"})()
    fake_response = type("Response", (), {"content": [fake_block]})()
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return fake_response

    highlights = {
        "best": [{
            "date": date(2026, 7, 10),
            "start_hour": 14,
            "end_hour": 16,
            "score": 4,
            "content": {
                "source": "transit",
                "planet": "Jupiter",
                "rule": {"summary": "Great fortune flows", "severity": "positive"},
            },
        }],
        "worst": [],
    }

    with patch.object(claude_service.settings, "get_setting", return_value=""), \
         patch.object(claude_service.client.messages, "create", side_effect=fake_create):
        claude_service.generate_interpretation(
            {"style": "warm"},
            {"Moon": {"sign": "Cancer", "house": 6}},
            [],
            calendar_highlights=highlights,
        )

    user_message = captured["messages"][0]["content"]
    assert "10.07.2026" in user_message
    assert "14:00–16:00" in user_message
    assert "Jupiter" in user_message
    assert "Great fortune flows" in user_message
    # Anleitung für die visuelle Tabelle wird nur MIT Kalender angefordert
    assert "Kalendertabelle" in user_message


def test_generate_interpretation_without_calendar_has_no_calendar_section():
    fake_block = type("Block", (), {"type": "text", "text": "Auswertung"})()
    fake_response = type("Response", (), {"content": [fake_block]})()
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return fake_response

    with patch.object(claude_service.settings, "get_setting", return_value=""), \
         patch.object(claude_service.client.messages, "create", side_effect=fake_create):
        claude_service.generate_interpretation(
            {"style": "warm"},
            {"Moon": {"sign": "Cancer", "house": 6}},
            [],
        )

    assert "Kalendertabelle" not in captured["messages"][0]["content"]
