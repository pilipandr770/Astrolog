"""
Место рождения (текст) -> координаты -> исторически корректный часовой пояс.

Историческая точность TZ важна: правила DST менялись много раз за XX век,
zoneinfo/pytz с базой tzdata это учитывают корректно при передаче
конкретной даты/времени, а не только текущего смещения.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
from app.config import Config

geolocator = Nominatim(user_agent=Config.GEOCODING_USER_AGENT)
tf = TimezoneFinder()


def geocode_place(place_name: str) -> dict:
    """place_name — свободный текст, например 'Frankfurt am Main, Germany'."""
    location = geolocator.geocode(place_name)
    if location is None:
        raise ValueError(f"Ort nicht gefunden: {place_name}")
    tz_name = tf.timezone_at(lat=location.latitude, lng=location.longitude)
    return {
        "lat": location.latitude,
        "lon": location.longitude,
        "tz_name": tz_name,
        "display_name": location.address,
    }


def local_to_utc_datetime(year: int, month: int, day: int, hour: int, minute: int, tz_name: str) -> datetime:
    """
    Wie local_to_utc_hour(), aber gibt das volle UTC-datetime zurück statt
    nur die Stunde. Wichtig, wenn die lokale Zeit nahe Mitternacht liegt und
    die Umrechnung auf ein anderes UTC-Kalenderdatum fällt — das würde
    local_to_utc_hour() stillschweigend verwerfen (nur .hour/.minute, kein
    Datumsversatz). Für swe.julday() braucht man Jahr/Monat/Tag UND Stunde
    aus demselben (ggf. verschobenen) UTC-Zeitpunkt.
    """
    local_dt = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(tz_name))
    return local_dt.astimezone(ZoneInfo("UTC"))


def local_to_utc_hour(year: int, month: int, day: int, hour: int, minute: int, tz_name: str) -> float:
    """
    Конвертирует локальное время рождения в десятичный UTC-час для
    передачи в swe.julday(). Учитывает исторический DST через zoneinfo.

    ВНИМАНИЕ: возвращает только час/минуту UTC, без даты — если локальное
    время рождения близко к полуночи и пересчёт в UTC сдвигает на другие
    сутки, вызывающий код должен использовать local_to_utc_datetime()
    вместо этого, чтобы не потерять сдвиг даты (см. natal_chart.py и
    transit_forecast.py).
    """
    utc_dt = local_to_utc_datetime(year, month, day, hour, minute, tz_name)
    return utc_dt.hour + utc_dt.minute / 60.0
