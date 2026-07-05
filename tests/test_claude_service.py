import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from unittest.mock import patch

from app.services import claude_service, jyotish


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
        blocks.append(type("ToolBlock", (), {
            "type": "tool_use", "name": "start_intake", "input": {"method": tool_called},
        })())
    return type("Response", (), {"content": blocks})()


def test_generate_sales_reply_not_ready_without_tool_call():
    fake_response = _fake_sales_response(text="Klar, frag gern weiter!")

    with patch.object(claude_service.settings, "get_setting", return_value=""), \
         patch.object(claude_service.client.messages, "create", return_value=fake_response) as mock_create:
        text, ready, method = claude_service.generate_sales_reply({}, [], "Was kostet das?")

    assert text == "Klar, frag gern weiter!"
    assert ready is False
    assert method is None
    assert mock_create.call_args.kwargs["tools"] == [claude_service.START_INTAKE_TOOL]
    sent_messages = mock_create.call_args.kwargs["messages"]
    assert sent_messages[-1] == {"role": "user", "content": "Was kostet das?"}


def test_generate_sales_reply_ready_when_tool_called():
    fake_response = _fake_sales_response(text="Super, dann los!", tool_called="jyotish")

    with patch.object(claude_service.settings, "get_setting", return_value=""), \
         patch.object(claude_service.client.messages, "create", return_value=fake_response):
        text, ready, method = claude_service.generate_sales_reply({}, [], "Ja, lass uns starten")

    assert text == "Super, dann los!"
    assert ready is True
    assert method == "jyotish"


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
            now_str="10.07.2026 09:15 Uhr (Europe/Berlin)",
        )

    assert text == "Klar, das heisst..."
    assert renew is False
    system_prompt = mock_create.call_args.kwargs["system"]
    assert "Dein Mond steht im 4. Haus" in system_prompt
    assert "2026-08-02" in system_prompt
    assert "10.07.2026 09:15 Uhr" in system_prompt
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


def _fake_dasha_effect(mahadasha_lord="Sun", antardasha_lord="Moon"):
    return jyotish.DashaEffect(
        rule_id=f"dasha_{mahadasha_lord.lower()}_{antardasha_lord.lower()}",
        mahadasha_lord=mahadasha_lord,
        antardasha_lord=antardasha_lord,
        summary="Testzusammenfassung der Dasha-Kombination.",
        severity="mixed",
        benefit_effects=[{"condition": "Moon exalted", "effect": "Gute Ernte."}],
        malefic_effects=[{"condition": "Moon in House 8", "effect": "Verlust."}],
        remedy="Charity of a white cow.",
    )


def test_generate_jyotish_teaser_includes_dasha_periods_and_effect():
    fake_block = type("Block", (), {"type": "text", "text": "Teaser-Text"})()
    fake_response = type("Response", (), {"content": [fake_block]})()
    mahadasha = {"lord": "Sun", "start_date": date(2020, 1, 1), "end_date": date(2026, 1, 1), "years": 6.0}
    antardasha = {"lord": "Moon", "start_date": date(2024, 1, 1), "end_date": date(2024, 11, 1), "years": 0.83}

    with patch.object(claude_service.settings, "get_setting", return_value=""), \
         patch.object(claude_service.client.messages, "create", return_value=fake_response) as mock_create:
        result = claude_service.generate_jyotish_teaser({}, mahadasha, antardasha, _fake_dasha_effect())

    assert result == "Teaser-Text"
    user_message = mock_create.call_args.kwargs["messages"][0]["content"]
    assert "Sun" in user_message
    assert "Moon" in user_message
    assert "Testzusammenfassung" in user_message
    assert mock_create.call_args.kwargs["system"] == claude_service.JYOTISH_TEASER_SYSTEM_PROMPT


def test_generate_jyotish_interpretation_includes_houses_and_month_section():
    fake_block = type("Block", (), {"type": "text", "text": "Auswertung"})()
    fake_response = type("Response", (), {"content": [fake_block]})()
    mahadasha = {"lord": "Sun", "start_date": date(2020, 1, 1), "end_date": date(2026, 1, 1), "years": 6.0}
    antardasha = {"lord": "Moon", "start_date": date(2024, 1, 1), "end_date": date(2024, 11, 1), "years": 0.83}
    month_segments = [{
        "start_date": date(2026, 7, 5), "end_date": date(2026, 8, 4),
        "mahadasha_lord": "Sun", "antardasha_lord": "Moon",
    }]

    with patch.object(claude_service.settings, "get_setting", return_value=""), \
         patch.object(claude_service.client.messages, "create", return_value=fake_response) as mock_create:
        result = claude_service.generate_jyotish_interpretation(
            {"style": "warm"}, {"Moon": {"sign": "Cancer", "house": 6}},
            mahadasha, antardasha, _fake_dasha_effect(), month_segments=month_segments,
        )
        assert mock_create.call_args.kwargs["system"] == claude_service._with_extra_instructions(claude_service.JYOTISH_SYSTEM_PROMPT)

    assert result == "Auswertung"
    user_message = mock_create.call_args.kwargs["messages"][0]["content"]
    assert "Cancer" in user_message
    assert "05.07.2026" in user_message
    assert "04.08.2026" in user_message


def test_generate_jyotish_interpretation_handles_missing_effect():
    fake_block = type("Block", (), {"type": "text", "text": "Auswertung"})()
    fake_response = type("Response", (), {"content": [fake_block]})()
    mahadasha = {"lord": "Sun", "start_date": date(2020, 1, 1), "end_date": date(2026, 1, 1), "years": 6.0}
    antardasha = {"lord": "Moon", "start_date": date(2024, 1, 1), "end_date": date(2024, 11, 1), "years": 0.83}

    with patch.object(claude_service.settings, "get_setting", return_value=""), \
         patch.object(claude_service.client.messages, "create", return_value=fake_response) as mock_create:
        claude_service.generate_jyotish_interpretation(
            {}, {}, mahadasha, antardasha, None,
        )

    user_message = mock_create.call_args.kwargs["messages"][0]["content"]
    assert "Keine Deutung" in user_message
