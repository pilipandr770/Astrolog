"""
Парсинг даты и времени рождения из свободного текста (WhatsApp-сообщения,
в т.ч. расшифрованные из голосовых). Без внешних NLP-зависимостей — набор
регулярок покрывает основные форматы, которыми реально пишут пользователи
на немецком и русском (аудитория продукта — DE-рынок, но разработка велась
и тестируется на русском, см. README).

Поддерживаемые форматы даты:
    15.05.1990 / 15/05/1990 / 15-05-1990 / 15.05.90 (двузначный год)
    1990-05-15 (ISO)
    15 мая 1990 / 15. Mai 1990 / 15 mai 1990

Поддерживаемые форматы времени:
    14:30 / 14.30 / 14-30 / 14 30 / 1430 / 14 Uhr 30 / 14 Uhr / 14
    'не знаю' / 'weiß nicht' и т.п. -> возвращается строка "unknown"
"""
import re
from datetime import date, datetime

MONTHS = {
    "январь": 1, "января": 1, "янв": 1,
    "февраль": 2, "февраля": 2, "фев": 2,
    "март": 3, "марта": 3,
    "апрель": 4, "апреля": 4, "апр": 4,
    "май": 5, "мая": 5,
    "июнь": 6, "июня": 6, "июн": 6,
    "июль": 7, "июля": 7, "июл": 7,
    "август": 8, "августа": 8, "авг": 8,
    "сентябрь": 9, "сентября": 9, "сен": 9, "сент": 9,
    "октябрь": 10, "октября": 10, "окт": 10,
    "ноябрь": 11, "ноября": 11, "нояб": 11, "ноя": 11,
    "декабрь": 12, "декабря": 12, "дек": 12,
    "januar": 1, "jan": 1,
    "februar": 2, "feb": 2,
    "märz": 3, "maerz": 3, "mär": 3,
    "april": 4, "apr": 4,
    "mai": 5,
    "juni": 6, "jun": 6,
    "juli": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "okt": 10,
    "november": 11, "nov": 11,
    "dezember": 12, "dez": 12,
}

_UNKNOWN_TIME_MARKERS = (
    "не знаю", "незнаю", "не помню", "непомню",
    "weiß nicht", "weiss nicht", "keine ahnung", "unbekannt",
)

_TIME_WORDS_RE = re.compile(r"(uhr|часов|часа|час|minuten|минут[а-я]*)")


def _normalize_year(year: int) -> int:
    if year >= 100:
        return year
    current_year = datetime.now().year
    full_century_guess = 2000 + year
    if full_century_guess > current_year:
        return 1900 + year
    return full_century_guess


def parse_birth_date(text: str) -> date | None:
    """Возвращает datetime.date, если удалось распознать дату, иначе None."""
    if not text:
        return None
    t = text.strip().lower()

    # ISO: yyyy-mm-dd / yyyy.mm.dd / yyyy/mm/dd
    m = re.search(r"\b(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})\b", t)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(year, month, day)
        except ValueError:
            pass

    # dd.mm.yyyy / dd/mm/yyyy / dd-mm-yyyy (yyyy или yy)
    m = re.search(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})\b", t)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(_normalize_year(int(m.group(3))))
        try:
            return date(year, month, day)
        except ValueError:
            pass

    # день + название месяца + год: "15 мая 1990", "15. Mai 1990"
    m = re.search(r"\b(\d{1,2})\.?\s+([a-zа-яё]+)\.?\s+(\d{4})\b", t)
    if m:
        day, month_word, year = int(m.group(1)), m.group(2), int(m.group(3))
        month = MONTHS.get(month_word)
        if month is None:
            for key, val in MONTHS.items():
                if month_word.startswith(key) or key.startswith(month_word):
                    month = val
                    break
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                pass

    return None


def parse_birth_time(text: str) -> tuple[int, int] | str | None:
    """
    Возвращает (hour, minute), строку "unknown" (пользователь не знает время)
    или None, если формат не распознан.
    """
    if not text:
        return None
    t = text.strip().lower()

    if any(marker in t for marker in _UNKNOWN_TIME_MARKERS):
        return "unknown"

    cleaned = _TIME_WORDS_RE.sub(" ", t)

    # два числа, разделённых чем угодно нецифровым (":", ".", "-", пробелы)
    m = re.search(r"(\d{1,2})\D+(\d{1,2})\b", cleaned)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour < 24 and 0 <= minute < 60:
            return (hour, minute)

    # слитно записанное время, напр. "1430"
    m = re.search(r"\b(\d{3,4})\b", cleaned)
    if m:
        digits = m.group(1)
        hour, minute = int(digits[:-2]), int(digits[-2:])
        if 0 <= hour < 24 and 0 <= minute < 60:
            return (hour, minute)

    # только час, напр. "14" / "14 Uhr"
    m = re.search(r"\b(\d{1,2})\b", cleaned)
    if m:
        hour = int(m.group(1))
        if 0 <= hour < 24:
            return (hour, 0)

    return None
