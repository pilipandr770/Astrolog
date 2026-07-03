"""
Расчёт натальной карты через Swiss Ephemeris (pyswisseph).

Используем СИДЕРИЧЕСКИЙ зодиак с аянамшей Lahiri — это стандарт для
ведической астрологии и, соответственно, для Лал Китаб (в отличие от
западной астрологии, которая использует тропический зодиак).

Этот модуль протестирован и работает. Если EPHE_PATH пустая или файлов
.se1 там нет, swisseph упадёт в приближённый Moshier-режим — работает,
но менее точно на границах веков. Для продакшена скачай файлы эфемерид,
см. docs/TODO.md.
"""
import swisseph as swe
from app.config import Config

swe.set_ephe_path(Config.EPHE_PATH)
swe.set_sid_mode(swe.SIDM_LAHIRI)

PLANETS = {
    "Sun": swe.SUN,
    "Moon": swe.MOON,
    "Mars": swe.MARS,
    "Mercury": swe.MERCURY,
    "Jupiter": swe.JUPITER,
    "Venus": swe.VENUS,
    "Saturn": swe.SATURN,
    "Rahu": swe.MEAN_NODE,  # Северный лунный узел
    # Кету (южный узел) считается как Rahu + 180°, отдельного ID в swisseph нет
}

SIGNS = [
    "Овен", "Телец", "Близнецы", "Рак", "Лев", "Дева",
    "Весы", "Скорпион", "Стрелец", "Козерог", "Водолей", "Рыбы",
]


def degrees_to_sign(degrees: float) -> dict:
    """Переводит абсолютный градус (0-360) в знак + градус внутри знака."""
    sign_index = int(degrees // 30)
    degree_in_sign = degrees % 30
    return {"sign": SIGNS[sign_index], "sign_index": sign_index, "degree": round(degree_in_sign, 2)}


def calculate_positions(year: int, month: int, day: int, hour: float, lat: float, lon: float) -> dict:
    """
    hour должен быть в UTC (десятичное число, например 14.5 = 14:30 UTC).
    Конвертацию из местного времени рождения в UTC делай ДО вызова этой
    функции — используй app.services.geocoding для получения TZ по месту
    рождения и корректно учитывай исторический DST.
    """
    jd = swe.julday(year, month, day, hour)
    flags = swe.FLG_SIDEREAL | swe.FLG_SWIEPH

    positions = {}
    for name, planet_id in PLANETS.items():
        pos, _ret_flags = swe.calc_ut(jd, planet_id, flags)
        longitude = pos[0]
        positions[name] = {
            "longitude": round(longitude, 4),
            **degrees_to_sign(longitude),
        }

    # Кету = Раху + 180°
    rahu_lon = positions["Rahu"]["longitude"]
    ketu_lon = (rahu_lon + 180) % 360
    positions["Ketu"] = {"longitude": round(ketu_lon, 4), **degrees_to_sign(ketu_lon)}

    # Асцендент (Лагна) — нужен для расчёта домов (бхав)
    houses = swe.houses_ex(jd, lat, lon, b"P", flags=swe.FLG_SIDEREAL)
    ascendant = houses[1][0]  # ascmc[0] = Ascendant
    positions["Ascendant"] = {"longitude": round(ascendant, 4), **degrees_to_sign(ascendant)}

    return positions


def assign_houses(positions: dict) -> dict:
    """
    Простое whole-sign house присвоение (типично для ведической традиции):
    дом = (знак планеты - знак асцендента) mod 12 + 1.
    Lal Kitab использует несколько иную, более специфическую логику домов
    ("пробуждённые"/"спящие" дома) — это НЕ то же самое, что классические
    бхавы. См. docs/LAL_KITAB_NOTES.md, доработать в lal_kitab.py.
    """
    asc_sign = positions["Ascendant"]["sign_index"]
    result = {}
    for name, data in positions.items():
        if name == "Ascendant":
            continue
        house = (data["sign_index"] - asc_sign) % 12 + 1
        result[name] = {**data, "house": house}
    return result
