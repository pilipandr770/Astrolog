import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.ephemeris import calculate_positions, assign_houses


def test_calculate_positions_returns_all_planets():
    positions = calculate_positions(1990, 5, 15, 14.5, lat=50.1109, lon=8.6821)  # Frankfurt
    expected_bodies = {"Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu", "Ascendant"}
    assert expected_bodies.issubset(positions.keys())
    for name, data in positions.items():
        assert 0 <= data["longitude"] < 360
        assert data["sign"] in [
            "Овен", "Телец", "Близнецы", "Рак", "Лев", "Дева",
            "Весы", "Скорпион", "Стрелец", "Козерог", "Водолей", "Рыбы",
        ]


def test_assign_houses():
    positions = calculate_positions(1990, 5, 15, 14.5, lat=50.1109, lon=8.6821)
    houses = assign_houses(positions)
    assert "Ascendant" not in houses  # ascendant не переносится в houses
    for name, data in houses.items():
        assert 1 <= data["house"] <= 12


def test_rahu_ketu_are_opposite():
    positions = calculate_positions(1990, 5, 15, 14.5, lat=50.1109, lon=8.6821)
    diff = abs(positions["Rahu"]["longitude"] - positions["Ketu"]["longitude"])
    assert abs(diff - 180) < 0.01
