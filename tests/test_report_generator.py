import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta
from unittest.mock import patch

from app.services import report_generator


def _paid_state(phone="491234567"):
    return {
        "phone": phone,
        "state": "paid",
        "paid": 1,
        "birth_date": "1990-05-15",
        "birth_time": "14:30",
        "birth_place": "Berlin, Deutschland",
        "birth_lat": 52.52,
        "birth_lon": 13.405,
        "birth_tz": "Europe/Berlin",
        "style": "warm",
    }


def _fake_chart():
    return {
        "positions": {},
        "houses": {"Moon": {"sign": "Cancer", "house": 4}},
        "findings": [],
        "rin_candidates": [],
        "house_activation": {},
        "is_time_approximate": False,
    }


def test_generate_and_send_report_happy_path(tmp_path):
    fake_calendar = [{"date": None, "slow_transits": {}, "blocks": []}]
    fake_highlights = {"best": [], "worst": []}

    with patch.object(report_generator, "REPORTS_DIR", str(tmp_path)), \
         patch.object(report_generator.conversation_state, "get_or_create", return_value=_paid_state()), \
         patch.object(report_generator.conversation_state, "update") as mock_update, \
         patch.object(report_generator.natal_chart, "compute", return_value=_fake_chart()), \
         patch.object(report_generator.transit_forecast, "build_monthly_calendar", return_value=fake_calendar), \
         patch.object(report_generator.transit_forecast, "pick_highlights", return_value=fake_highlights), \
         patch.object(report_generator.claude_service, "generate_interpretation", return_value="Text") as mock_claude, \
         patch.object(report_generator.pdf_generator, "generate_report_pdf") as mock_pdf, \
         patch.object(report_generator.messaging, "send_document") as mock_doc:
        assert report_generator.generate_and_send_report("491234567") is True

    # Das volle conversation_state-Dict geht an Claude — language_hint/
    # language_sample/style stecken darin (siehe _language_directive).
    assert mock_claude.call_args[0][0] == _paid_state()
    assert mock_claude.call_args.kwargs["calendar_highlights"] == fake_highlights
    mock_pdf.assert_called_once()
    birth_display = mock_pdf.call_args[0][1]
    assert birth_display == {
        "date": "15.05.1990",
        "time": "14:30",
        "place": "Berlin, Deutschland",
    }
    assert mock_pdf.call_args.kwargs["calendar"] == fake_calendar
    mock_doc.assert_called_once()
    expected_end_date = (date.today() + timedelta(days=report_generator.CALENDAR_DAYS - 1)).isoformat()
    mock_update.assert_called_once_with(
        "491234567", state="report_sent", last_interpretation="Text",
        post_report_chat_history=None, report_calendar_end_date=expected_end_date,
    )


def test_generate_and_send_report_survives_calendar_failure(tmp_path):
    # Kalender-Fehler darf den Bericht NICHT verhindern — er geht ohne
    # Kalender raus (calendar=None, calendar_highlights=None).
    with patch.object(report_generator, "REPORTS_DIR", str(tmp_path)), \
         patch.object(report_generator.conversation_state, "get_or_create", return_value=_paid_state()), \
         patch.object(report_generator.conversation_state, "update") as mock_update, \
         patch.object(report_generator.natal_chart, "compute", return_value=_fake_chart()), \
         patch.object(report_generator.transit_forecast, "build_monthly_calendar", side_effect=RuntimeError("swe")), \
         patch.object(report_generator.claude_service, "generate_interpretation", return_value="Text") as mock_claude, \
         patch.object(report_generator.pdf_generator, "generate_report_pdf") as mock_pdf, \
         patch.object(report_generator.messaging, "send_document"):
        assert report_generator.generate_and_send_report("491234567") is True

    assert mock_claude.call_args.kwargs["calendar_highlights"] is None
    assert mock_pdf.call_args.kwargs["calendar"] is None
    mock_update.assert_called_once_with(
        "491234567", state="report_sent", last_interpretation="Text",
        post_report_chat_history=None, report_calendar_end_date=None,
    )


def test_short_place_keeps_city_and_country():
    long_name = (
        "Чернігів, Чернігівська міська громада, Чернігівський район, "
        "Чернігівська область, 14000-14499, Україна"
    )
    assert report_generator._short_place(long_name) == "Чернігів, Україна"
    assert report_generator._short_place("Berlin, Deutschland") == "Berlin, Deutschland"
    assert report_generator._short_place("Berlin") == "Berlin"
    assert report_generator._short_place("") == ""


def test_generate_and_send_report_marks_approximate_time(tmp_path):
    state = _paid_state()
    state["birth_time"] = "unbekannt"
    chart = _fake_chart()
    chart["is_time_approximate"] = True

    with patch.object(report_generator, "REPORTS_DIR", str(tmp_path)), \
         patch.object(report_generator.conversation_state, "get_or_create", return_value=state), \
         patch.object(report_generator.conversation_state, "update"), \
         patch.object(report_generator.natal_chart, "compute", return_value=chart), \
         patch.object(report_generator.transit_forecast, "build_monthly_calendar", return_value=[]), \
         patch.object(report_generator.transit_forecast, "pick_highlights", return_value={"best": [], "worst": []}), \
         patch.object(report_generator.claude_service, "generate_interpretation", return_value="Text"), \
         patch.object(report_generator.pdf_generator, "generate_report_pdf") as mock_pdf, \
         patch.object(report_generator.messaging, "send_document"):
        report_generator.generate_and_send_report("491234567")

    assert "~12:00" in mock_pdf.call_args[0][1]["time"]


def test_generate_and_send_report_failure_keeps_paid_state_and_apologizes():
    with patch.object(report_generator.conversation_state, "get_or_create", return_value=_paid_state()), \
         patch.object(report_generator.conversation_state, "update") as mock_update, \
         patch.object(report_generator.natal_chart, "compute", side_effect=RuntimeError("boom")), \
         patch.object(report_generator.messaging, "send_text") as mock_text:
        assert report_generator.generate_and_send_report("491234567") is False

    mock_update.assert_not_called()  # bleibt "paid" -> Retry bei nächster Nachricht
    mock_text.assert_called_once()
    assert "Fehler" in mock_text.call_args[0][1]


def test_generate_and_send_report_skips_if_not_paid():
    state = _paid_state()
    state["state"] = "awaiting_payment"
    with patch.object(report_generator.conversation_state, "get_or_create", return_value=state), \
         patch.object(report_generator.natal_chart, "compute") as mock_compute:
        assert report_generator.generate_and_send_report("491234567") is False
    mock_compute.assert_not_called()


def test_generate_and_send_report_skips_concurrent_duplicate():
    report_generator._GENERATING.add("491234567")
    try:
        with patch.object(report_generator.conversation_state, "get_or_create") as mock_get:
            assert report_generator.generate_and_send_report("491234567") is False
        mock_get.assert_not_called()
    finally:
        report_generator._GENERATING.discard("491234567")


def test_compute_today_snapshot_returns_first_day_of_single_day_calendar():
    fake_calendar = [{"date": date.today(), "slow_transits": {}, "blocks": [{"start_hour": 0}]}]

    with patch.object(report_generator.natal_chart, "compute", return_value=_fake_chart()), \
         patch.object(report_generator.transit_forecast, "build_monthly_calendar", return_value=fake_calendar) as mock_cal:
        result = report_generator.compute_today_snapshot(_paid_state())

    assert result == fake_calendar[0]
    assert mock_cal.call_args.kwargs["days"] == 1
    assert mock_cal.call_args.kwargs["start_date"] == date.today()


def test_compute_today_snapshot_returns_none_on_error():
    with patch.object(report_generator.natal_chart, "compute", side_effect=RuntimeError("swe")):
        assert report_generator.compute_today_snapshot(_paid_state()) is None


def _jyotish_state(phone="491234567"):
    state = _paid_state(phone)
    state["astro_method"] = "jyotish"
    return state


def _fake_chart_with_moon():
    chart = _fake_chart()
    chart["positions"] = {"Moon": {"longitude": 45.0, "sign": "Taurus"}}
    return chart


def _fake_current_dasha():
    return {
        "mahadasha": {"lord": "Sun", "start_date": date(2020, 1, 1), "end_date": date(2026, 1, 1), "years": 6.0},
        "antardasha": {"lord": "Moon", "start_date": date(2024, 1, 1), "end_date": date(2024, 11, 1), "years": 0.83},
    }


def test_generate_and_send_report_dispatches_to_jyotish_path(tmp_path):
    fake_segments = [{
        "start_date": date.today(), "end_date": date.today() + timedelta(days=30),
        "mahadasha_lord": "Sun", "antardasha_lord": "Moon",
    }]
    fake_effect = object()

    with patch.object(report_generator, "REPORTS_DIR", str(tmp_path)), \
         patch.object(report_generator.conversation_state, "get_or_create", return_value=_jyotish_state()), \
         patch.object(report_generator.conversation_state, "update") as mock_update, \
         patch.object(report_generator.natal_chart, "compute", return_value=_fake_chart_with_moon()), \
         patch.object(report_generator.dasha, "compute_current_dasha", return_value=_fake_current_dasha()), \
         patch.object(report_generator.dasha, "compute_month_segments", return_value=fake_segments), \
         patch.object(report_generator.jyotish, "get_dasha_effect", return_value=fake_effect) as mock_effect, \
         patch.object(report_generator.claude_service, "generate_jyotish_interpretation", return_value="Jyotish-Text") as mock_claude, \
         patch.object(report_generator.pdf_generator, "generate_jyotish_report_pdf") as mock_pdf, \
         patch.object(report_generator.messaging, "send_document") as mock_doc:
        assert report_generator.generate_and_send_report("491234567") is True

    mock_effect.assert_called_once_with("Sun", "Moon")
    mock_claude.assert_called_once()
    assert mock_claude.call_args[0][2] == _fake_current_dasha()["mahadasha"]
    assert mock_claude.call_args[0][3] == _fake_current_dasha()["antardasha"]
    assert mock_claude.call_args.kwargs["month_segments"] == fake_segments
    mock_pdf.assert_called_once()
    assert mock_pdf.call_args[0][1] == {
        "date": "15.05.1990", "time": "14:30", "place": "Berlin, Deutschland",
    }
    assert mock_pdf.call_args.kwargs["segments"] == fake_segments
    mock_doc.assert_called_once()
    assert mock_doc.call_args[0][2] == "Jyotish-Auswertung.pdf"
    expected_end_date = (date.today() + timedelta(days=report_generator.CALENDAR_DAYS - 1)).isoformat()
    mock_update.assert_called_once_with(
        "491234567", state="report_sent", last_interpretation="Jyotish-Text",
        post_report_chat_history=None, report_calendar_end_date=expected_end_date,
    )


def test_generate_and_send_report_jyotish_fails_beyond_dasha_horizon():
    with patch.object(report_generator.conversation_state, "get_or_create", return_value=_jyotish_state()), \
         patch.object(report_generator.conversation_state, "update") as mock_update, \
         patch.object(report_generator.natal_chart, "compute", return_value=_fake_chart_with_moon()), \
         patch.object(report_generator.dasha, "compute_current_dasha", return_value={"mahadasha": None, "antardasha": None}), \
         patch.object(report_generator.messaging, "send_text") as mock_text:
        assert report_generator.generate_and_send_report("491234567") is False

    mock_update.assert_not_called()
    mock_text.assert_called_once()


def test_compute_jyotish_today_snapshot_returns_dasha_and_effect():
    fake_effect = object()
    with patch.object(report_generator.natal_chart, "compute", return_value=_fake_chart_with_moon()), \
         patch.object(report_generator.dasha, "compute_current_dasha", return_value=_fake_current_dasha()), \
         patch.object(report_generator.jyotish, "get_dasha_effect", return_value=fake_effect):
        result = report_generator.compute_jyotish_today_snapshot(_jyotish_state())

    assert result["mahadasha"] == _fake_current_dasha()["mahadasha"]
    assert result["antardasha"] == _fake_current_dasha()["antardasha"]
    assert result["effect"] is fake_effect


def test_compute_jyotish_today_snapshot_returns_none_beyond_horizon():
    with patch.object(report_generator.natal_chart, "compute", return_value=_fake_chart_with_moon()), \
         patch.object(report_generator.dasha, "compute_current_dasha", return_value={"mahadasha": None, "antardasha": None}):
        assert report_generator.compute_jyotish_today_snapshot(_jyotish_state()) is None


def test_compute_jyotish_today_snapshot_returns_none_on_error():
    with patch.object(report_generator.natal_chart, "compute", side_effect=RuntimeError("swe")):
        assert report_generator.compute_jyotish_today_snapshot(_jyotish_state()) is None
