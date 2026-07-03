"""
Zentrale Berechnung: conversation_state (Geburtsdaten) -> vollständige
astrologische Auswertung (Positionen, Häuser, Lal-Kitab-Befunde, Rin-
Kandidaten, Haus-Aktivierung). Wird sowohl vom kostenlosen Teaser
(dialog_manager._send_teaser) als auch vom künftigen bezahlten PDF-Bericht
(docs/TODO.md Punkt 4) verwendet, um die Berechnung nicht doppelt zu
pflegen.
"""
from datetime import date

from app.services import ephemeris, geocoding, lal_kitab


def resolve_birth_hour(birth_time: str) -> tuple[int, int, bool]:
    """
    Gibt (hour, minute, is_approximate) zurück.

    'unbekannt' (siehe dialog_manager/message_parser) -> 12:00 Uhr als
    Näherung, is_approximate=True, damit Aufrufer das im Text kennzeichnen
    können (Hausansätze sind ohne genaue Geburtszeit weniger zuverlässig).
    """
    if birth_time == "unbekannt":
        return 12, 0, True
    hour_str, minute_str = birth_time.split(":")
    return int(hour_str), int(minute_str), False


def compute(state: dict) -> dict:
    """
    state — ein conversation_state-Dict mit birth_date (ISO), birth_time
    ("HH:MM" oder "unbekannt"), birth_lat, birth_lon, birth_tz.
    """
    birth_date = date.fromisoformat(state["birth_date"])
    hour, minute, is_approximate = resolve_birth_hour(state["birth_time"])

    # local_to_utc_datetime (nicht local_to_utc_hour!) — bei Geburtszeiten
    # nahe Mitternacht kann die Umrechnung nach UTC auf ein anderes Datum
    # fallen; das muss für swe.julday() berücksichtigt werden.
    utc_dt = geocoding.local_to_utc_datetime(
        birth_date.year, birth_date.month, birth_date.day, hour, minute, state["birth_tz"],
    )
    utc_hour = utc_dt.hour + utc_dt.minute / 60.0
    positions = ephemeris.calculate_positions(
        utc_dt.year, utc_dt.month, utc_dt.day, utc_hour,
        state["birth_lat"], state["birth_lon"],
    )
    houses = ephemeris.assign_houses(positions)
    findings = lal_kitab.analyze(houses)
    rin_candidates = lal_kitab.detect_rin(houses)
    house_activation = lal_kitab.compute_house_activation(houses)

    return {
        "positions": positions,
        "houses": houses,
        "findings": findings,
        "rin_candidates": rin_candidates,
        "house_activation": house_activation,
        "is_time_approximate": is_approximate,
    }
