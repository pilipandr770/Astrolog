"""
Транзитный календарь на месяц — почасовая (2-часовыми блоками) разметка
того, какой натальный дом сейчас "активен" и что там происходит. См.
обсуждение в чате и docs/TODO.md п.9 — ключевые решения:

1. Три временных слоя, как их описал пользователь:
   - Лагна (восходящий знак) меняется каждые ~2 часа (вращение Земли) —
     самая мелкая единица календаря (BLOCK_HOURS).
   - Луна — самая быстрая ИЗ ПЛАНЕТ, меняет знак/дом раз в ~2-3 дня.
   - Остальные тела (Sun, Mercury, Venus, Mars, Jupiter, Saturn, Rahu,
     Ketu) — от недель до лет; в пределах одного месяца достаточно считать
     их положение раз в день (в течение дня они не меняют знак).

2. Интерпретация НЕ выдумывает новые "transit"-формулировки — у
   первоисточника нет отдельной главы про реальные транзиты (Chapter 12,
   "Annual Predictions", оказался числовым 35-летним циклом возрастных
   периодов планет, а не расчётом положений). Вместо этого каждый блок
   трактуется через уже проверенные натальные правила
   (docs/lal_kitab_rules.yaml) — либо через ТРАНЗИТНУЮ планету, если она
   сейчас проходит тот же натальный дом, что и активная Лагна (это и есть
   моменты вида "пока Марс на твоей стороне" из примера пользователя),
   либо, если такого совпадения нет, через НАТАЛЬНОГО хозяина этого дома
   как базовый фон. Оба случая явно помечены полем content["source"].

3. Полные положения планет считает ephemeris.calculate_positions() (тот
   же расчёт, что и для натальной карты) — здесь только накладываем
   результат на НАТАЛЬНЫЕ дома (через натальный Асцендент), а не строим
   отдельную "карту момента".
"""
from datetime import date, timedelta

from app.services import ephemeris, geocoding, lal_kitab

BLOCK_HOURS = 2
TRANSIT_PLANETS = ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu")
_SEVERITY_SCORE = {"positive": 2, "caution": -2, "mixed": 0, "neutral": 0}


def _house_from_sign(sign_index: int, natal_ascendant_sign_index: int) -> int:
    """Dieselbe Whole-Sign-Formel wie ephemeris.assign_houses()."""
    return (sign_index - natal_ascendant_sign_index) % 12 + 1


def _positions_at(on_date: date, hour_utc: float, lat: float, lon: float) -> dict:
    return ephemeris.calculate_positions(on_date.year, on_date.month, on_date.day, hour_utc, lat, lon)


def compute_day_transits(
    on_date: date, noon_hour_utc: float, lat: float, lon: float, natal_ascendant_sign_index: int
) -> dict:
    """Position der 9 Himmelskörper für einen Tag — gilt näherungsweise für den ganzen Tag."""
    positions = _positions_at(on_date, noon_hour_utc, lat, lon)
    result = {}
    for planet in TRANSIT_PLANETS:
        sign_index = positions[planet]["sign_index"]
        house = _house_from_sign(sign_index, natal_ascendant_sign_index)
        result[planet] = {"house": house, "rule": lal_kitab.get_rule(planet, house)}
    return result


def compute_lagna_house(
    on_date: date, hour_utc: float, lat: float, lon: float, natal_ascendant_sign_index: int
) -> int:
    positions = _positions_at(on_date, hour_utc, lat, lon)
    sign_index = positions["Ascendant"]["sign_index"]
    return _house_from_sign(sign_index, natal_ascendant_sign_index)


def _block_content(lagna_house: int, slow_transits: dict, natal_occupant_by_house: dict) -> dict | None:
    """
    Bevorzugt eine transitierende Planet-Übereinstimmung (source="transit")
    — das sind die hervorgehobenen Momente wie "während Mars auf deiner
    Seite ist" aus dem Chat-Beispiel. Ohne Übereinstimmung: Rückgriff auf
    den natalen Hausherren als Grundton (source="natal").
    """
    for planet, info in slow_transits.items():
        if info["house"] == lagna_house and info["rule"]:
            return {"source": "transit", "planet": planet, "rule": info["rule"]}

    natal_finding = natal_occupant_by_house.get(lagna_house)
    if natal_finding:
        return {
            "source": "natal",
            "planet": natal_finding.planet,
            "rule": {"summary": natal_finding.summary, "severity": natal_finding.severity},
        }
    return None


def build_monthly_calendar(
    chart: dict, lat: float, lon: float, tz_name: str, start_date: date, days: int = 30
) -> list[dict]:
    """
    chart — Ergebnis von app.services.natal_chart.compute() (braucht
    positions["Ascendant"] und findings).
    lat/lon/tz_name — aktueller Aufenthaltsort für den Kalender (Näherung:
    Geburtsort, falls kein separater Wohnort erfasst wird).
    """
    natal_ascendant_sign_index = chart["positions"]["Ascendant"]["sign_index"]
    natal_occupant_by_house = {f.house: f for f in chart["findings"]}

    calendar = []
    for day_offset in range(days):
        on_date = start_date + timedelta(days=day_offset)

        noon_utc_dt = geocoding.local_to_utc_datetime(on_date.year, on_date.month, on_date.day, 12, 0, tz_name)
        noon_hour_utc = noon_utc_dt.hour + noon_utc_dt.minute / 60.0
        slow_transits = compute_day_transits(
            date(noon_utc_dt.year, noon_utc_dt.month, noon_utc_dt.day),
            noon_hour_utc, lat, lon, natal_ascendant_sign_index,
        )

        blocks = []
        for block_index in range(24 // BLOCK_HOURS):
            local_hour = block_index * BLOCK_HOURS
            utc_dt = geocoding.local_to_utc_datetime(on_date.year, on_date.month, on_date.day, local_hour, 0, tz_name)
            utc_hour = utc_dt.hour + utc_dt.minute / 60.0
            lagna_house = compute_lagna_house(
                date(utc_dt.year, utc_dt.month, utc_dt.day), utc_hour, lat, lon, natal_ascendant_sign_index,
            )
            blocks.append({
                "start_hour": local_hour,
                "end_hour": local_hour + BLOCK_HOURS,
                "lagna_house": lagna_house,
                "content": _block_content(lagna_house, slow_transits, natal_occupant_by_house),
            })

        calendar.append({"date": on_date, "slow_transits": slow_transits, "blocks": blocks})
    return calendar


def pick_highlights(calendar: list[dict], top_n: int = 5) -> dict:
    """
    Wählt die auffälligsten Fenster für die Kurzfassung im PDF/Teaser:
    "beste" (positive Übereinstimmungen) und "schlechteste" (caution).
    Transit-Übereinstimmungen zählen doppelt so stark wie reine
    Natal-Grundtöne, da sie die eigentlich hervorgehobenen Momente sind.
    """
    scored = []
    for day in calendar:
        for block in day["blocks"]:
            content = block.get("content")
            if not content:
                continue
            score = _SEVERITY_SCORE.get(content["rule"]["severity"], 0)
            if content["source"] == "transit":
                score *= 2
            if score == 0:
                continue
            scored.append({
                "date": day["date"],
                "start_hour": block["start_hour"],
                "end_hour": block["end_hour"],
                "score": score,
                "content": content,
            })

    best = sorted([b for b in scored if b["score"] > 0], key=lambda b: b["score"], reverse=True)[:top_n]
    worst = sorted([b for b in scored if b["score"] < 0], key=lambda b: b["score"])[:top_n]
    return {"best": best, "worst": worst}
