import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from app.services import claude_service


def test_with_extra_instructions_passthrough_when_empty():
    with patch.object(claude_service.settings, "get_setting", return_value=""):
        result = claude_service._with_extra_instructions("BASE PROMPT")
    assert result == "BASE PROMPT"


def test_with_extra_instructions_appends_when_set():
    with patch.object(claude_service.settings, "get_setting", return_value="Sei besonders freundlich."):
        result = claude_service._with_extra_instructions("BASE PROMPT")
    assert "BASE PROMPT" in result
    assert "Sei besonders freundlich." in result
    assert result.index("BASE PROMPT") < result.index("Sei besonders freundlich.")


def test_generate_teaser_uses_extra_instructions_and_returns_text():
    fake_block = type("Block", (), {"type": "text", "text": "Teaser-Text"})()
    fake_response = type("Response", (), {"content": [fake_block]})()

    with patch.object(claude_service.settings, "get_setting", return_value=""), \
         patch.object(claude_service.client.messages, "create", return_value=fake_response) as mock_create:
        result = claude_service.generate_teaser(
            {"birth_date": "1990-05-15"},
            {"Moon": {"sign": "Cancer", "house": 6}},
            [],
        )

    assert result == "Teaser-Text"
    mock_create.assert_called_once()
    assert mock_create.call_args.kwargs["system"] == claude_service.TEASER_SYSTEM_PROMPT
