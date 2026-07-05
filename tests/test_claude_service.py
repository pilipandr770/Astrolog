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


def _fake_sales_response(text=None, tool_called=False):
    blocks = []
    if text is not None:
        blocks.append(type("TextBlock", (), {"type": "text", "text": text})())
    if tool_called:
        blocks.append(type("ToolBlock", (), {"type": "tool_use", "name": "start_intake"})())
    return type("Response", (), {"content": blocks})()


def test_generate_sales_reply_not_ready_without_tool_call():
    fake_response = _fake_sales_response(text="Klar, frag gern weiter!")

    with patch.object(claude_service.settings, "get_setting", return_value=""), \
         patch.object(claude_service.client.messages, "create", return_value=fake_response) as mock_create:
        text, ready = claude_service.generate_sales_reply({}, [], "Was kostet das?")

    assert text == "Klar, frag gern weiter!"
    assert ready is False
    assert mock_create.call_args.kwargs["tools"] == [claude_service.START_INTAKE_TOOL]
    sent_messages = mock_create.call_args.kwargs["messages"]
    assert sent_messages[-1] == {"role": "user", "content": "Was kostet das?"}


def test_generate_sales_reply_ready_when_tool_called():
    fake_response = _fake_sales_response(text="Super, dann los!", tool_called=True)

    with patch.object(claude_service.settings, "get_setting", return_value=""), \
         patch.object(claude_service.client.messages, "create", return_value=fake_response):
        text, ready = claude_service.generate_sales_reply({}, [], "Ja, lass uns starten")

    assert text == "Super, dann los!"
    assert ready is True


def test_generate_sales_reply_includes_prior_history_in_messages():
    fake_response = _fake_sales_response(text="Antwort")
    history = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hallo! Wie kann ich helfen?"},
    ]

    with patch.object(claude_service.settings, "get_setting", return_value=""), \
         patch.object(claude_service.client.messages, "create", return_value=fake_response) as mock_create:
        claude_service.generate_sales_reply({}, history, "Was genau macht ihr?")

    sent_messages = mock_create.call_args.kwargs["messages"]
    assert sent_messages[0] == history[0]
    assert sent_messages[1] == history[1]
    assert sent_messages[2] == {"role": "user", "content": "Was genau macht ihr?"}


def _fake_post_report_response(text=None, tool_called=False):
    blocks = []
    if text is not None:
        blocks.append(type("TextBlock", (), {"type": "text", "text": text})())
    if tool_called:
        blocks.append(type("ToolBlock", (), {"type": "tool_use", "name": "start_renewal"})())
    return type("Response", (), {"content": blocks})()


def test_generate_post_report_reply_includes_report_context_and_history():
    fake_response = _fake_post_report_response(text="Klar, das heisst...")
    history = [{"role": "user", "content": "Danke fuer den Bericht!"}]

    with patch.object(claude_service.settings, "get_setting", return_value=""), \
         patch.object(claude_service.client.messages, "create", return_value=fake_response) as mock_create:
        text, renew = claude_service.generate_post_report_reply(
            {"style": "warm"},
            "Dein Mond steht im 4. Haus und bedeutet finanziellen Wandel.",
            history,
            "Was heisst das fuer meine Finanzen?",
            calendar_end_date="2026-08-02",
            today_str="2026-07-10",
        )

    assert text == "Klar, das heisst..."
    assert renew is False
    system_prompt = mock_create.call_args.kwargs["system"]
    assert "Dein Mond steht im 4. Haus" in system_prompt
    assert "2026-08-02" in system_prompt
    assert "2026-07-10" in system_prompt
    assert mock_create.call_args.kwargs["tools"] == [claude_service.START_RENEWAL_TOOL]
    sent_messages = mock_create.call_args.kwargs["messages"]
    assert sent_messages[0] == history[0]
    assert sent_messages[-1] == {"role": "user", "content": "Was heisst das fuer meine Finanzen?"}


def test_format_today_snapshot_empty_without_data():
    assert claude_service._format_today_snapshot(None) == ""
    assert claude_service._format_today_snapshot({"date": None, "blocks": []}) == ""


def test_format_today_snapshot_formats_blocks_with_severity_and_source():
    from datetime import date

    snapshot = {
        "date": date(2026, 7, 5),
        "blocks": [
            {
                "start_hour": 6, "end_hour": 8, "lagna_house": 5,
                "content": {"source": "transit", "planet": "Mercury", "rule": {"summary": "Worte wirken", "severity": "positive"}},
            },
            {"start_hour": 8, "end_hour": 10, "lagna_house": 6, "content": None},
        ],
    }
    formatted = claude_service._format_today_snapshot(snapshot)
    assert "05.07.2026" in formatted
    assert "06:00–08:00" in formatted
    assert "Mercury" in formatted
    assert "Transit" in formatted
    assert "Worte wirken" in formatted


def test_generate_post_report_reply_includes_today_snapshot_in_system_prompt():
    from datetime import date

    fake_response = _fake_post_report_response(text="Heute ist gut fuers Reden.")
    snapshot = {
        "date": date(2026, 7, 5),
        "blocks": [{
            "start_hour": 6, "end_hour": 8, "lagna_house": 5,
            "content": {"source": "transit", "planet": "Mercury", "rule": {"summary": "Worte wirken", "severity": "positive"}},
        }],
    }

    with patch.object(claude_service.settings, "get_setting", return_value=""), \
         patch.object(claude_service.client.messages, "create", return_value=fake_response) as mock_create:
        claude_service.generate_post_report_reply(
            {}, "Bericht-Text", [], "Wie wird mein Tag heute?", today_snapshot=snapshot,
        )

    assert "Mercury" in mock_create.call_args.kwargs["system"]


def test_generate_post_report_reply_renew_true_when_tool_called():
    fake_response = _fake_post_report_response(text="Perfekt, ich erstelle dir die Fortsetzung.", tool_called=True)

    with patch.object(claude_service.settings, "get_setting", return_value=""), \
         patch.object(claude_service.client.messages, "create", return_value=fake_response):
        text, renew = claude_service.generate_post_report_reply(
            {}, "Bericht-Text", [], "Ja, mach das bitte"
        )

    assert text == "Perfekt, ich erstelle dir die Fortsetzung."
    assert renew is True
