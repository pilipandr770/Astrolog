import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import natal_chart

FRANKFURT_STATE = {
    "birth_date": "1990-05-15",
    "birth_time": "14:30",
    "birth_lat": 50.1109,
    "birth_lon": 8.6821,
    "birth_tz": "Europe/Berlin",
}


def test_resolve_birth_hour_known_time():
    hour, minute, is_approximate = natal_chart.resolve_birth_hour("14:30")
    assert (hour, minute, is_approximate) == (14, 30, False)


def test_resolve_birth_hour_unknown_defaults_to_noon():
    hour, minute, is_approximate = natal_chart.resolve_birth_hour("unbekannt")
    assert (hour, minute, is_approximate) == (12, 0, True)


def test_compute_returns_full_chart_structure():
    chart = natal_chart.compute(FRANKFURT_STATE)

    assert set(chart.keys()) == {
        "positions", "houses", "findings", "rin_candidates",
        "house_activation", "is_time_approximate",
    }
    assert chart["is_time_approximate"] is False
    # Jeder der 9 Körper landet in genau einem Haus -> genau ein Fund pro Körper.
    assert len(chart["findings"]) == 9
    assert len(chart["house_activation"]) == 12


def test_compute_marks_approximate_time_when_unknown():
    state = dict(FRANKFURT_STATE, birth_time="unbekannt")
    chart = natal_chart.compute(state)
    assert chart["is_time_approximate"] is True
