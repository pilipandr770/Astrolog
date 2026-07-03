import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date

from app.services import natal_chart, transit_forecast

FRANKFURT_STATE = {
    "birth_date": "1990-05-15",
    "birth_time": "14:30",
    "birth_lat": 50.1109,
    "birth_lon": 8.6821,
    "birth_tz": "Europe/Berlin",
}


def _chart():
    return natal_chart.compute(FRANKFURT_STATE)


def test_house_from_sign_wraps_around():
    assert transit_forecast._house_from_sign(0, 0) == 1
    assert transit_forecast._house_from_sign(11, 0) == 12
    assert transit_forecast._house_from_sign(0, 11) == 2  # (0-11)%12+1 = 1+1


def test_compute_day_transits_covers_all_nine_bodies():
    chart = _chart()
    natal_asc = chart["positions"]["Ascendant"]["sign_index"]
    transits = transit_forecast.compute_day_transits(
        date(2027, 6, 17), 10.0, FRANKFURT_STATE["birth_lat"], FRANKFURT_STATE["birth_lon"], natal_asc
    )
    assert set(transits.keys()) == set(transit_forecast.TRANSIT_PLANETS)
    for info in transits.values():
        assert 1 <= info["house"] <= 12
        assert info["rule"] is not None  # alle 108 Kombinationen sind abgedeckt


def test_build_monthly_calendar_structure():
    chart = _chart()
    calendar = transit_forecast.build_monthly_calendar(
        chart, FRANKFURT_STATE["birth_lat"], FRANKFURT_STATE["birth_lon"],
        FRANKFURT_STATE["birth_tz"], start_date=date(2027, 6, 17), days=5,
    )
    assert len(calendar) == 5
    for day in calendar:
        assert len(day["blocks"]) == 12  # 24h / 2h Blöcke
        assert set(day["slow_transits"].keys()) == set(transit_forecast.TRANSIT_PLANETS)
        for block in day["blocks"]:
            assert block["end_hour"] - block["start_hour"] == transit_forecast.BLOCK_HOURS
            assert 1 <= block["lagna_house"] <= 12
            # Jeder Block hat Inhalt, da jedes Haus entweder transitierend
            # oder natal besetzt ist (9 Körper über 12 Häuser -> nicht
            # jedes Haus hat zwingend einen natalen Bewohner, aber i.d.R
            # ist zumindest ein transitierender Treffer da).


def test_build_monthly_calendar_blocks_have_valid_content_when_present():
    chart = _chart()
    calendar = transit_forecast.build_monthly_calendar(
        chart, FRANKFURT_STATE["birth_lat"], FRANKFURT_STATE["birth_lon"],
        FRANKFURT_STATE["birth_tz"], start_date=date(2027, 6, 17), days=2,
    )
    for day in calendar:
        for block in day["blocks"]:
            content = block["content"]
            if content is not None:
                assert content["source"] in ("transit", "natal")
                assert "severity" in content["rule"]


def test_pick_highlights_returns_best_and_worst():
    chart = _chart()
    calendar = transit_forecast.build_monthly_calendar(
        chart, FRANKFURT_STATE["birth_lat"], FRANKFURT_STATE["birth_lon"],
        FRANKFURT_STATE["birth_tz"], start_date=date(2027, 6, 17), days=30,
    )
    highlights = transit_forecast.pick_highlights(calendar, top_n=5)
    assert set(highlights.keys()) == {"best", "worst"}
    assert len(highlights["best"]) <= 5
    assert len(highlights["worst"]) <= 5
    assert all(h["score"] > 0 for h in highlights["best"])
    assert all(h["score"] < 0 for h in highlights["worst"])
    # Beste Treffer absteigend, schlechteste aufsteigend sortiert (stärkste zuerst)
    scores_best = [h["score"] for h in highlights["best"]]
    assert scores_best == sorted(scores_best, reverse=True)
    scores_worst = [h["score"] for h in highlights["worst"]]
    assert scores_worst == sorted(scores_worst)
