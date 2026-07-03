import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from app.services.message_parser import parse_birth_date, parse_birth_time


def test_parse_date_numeric_dot():
    assert parse_birth_date("15.05.1990") == date(1990, 5, 15)


def test_parse_date_numeric_slash():
    assert parse_birth_date("15/05/1990") == date(1990, 5, 15)


def test_parse_date_two_digit_year():
    assert parse_birth_date("15.05.90") == date(1990, 5, 15)


def test_parse_date_iso():
    assert parse_birth_date("1990-05-15") == date(1990, 5, 15)


def test_parse_date_russian_month_name():
    assert parse_birth_date("15 мая 1990") == date(1990, 5, 15)


def test_parse_date_german_month_name():
    assert parse_birth_date("15. Mai 1990") == date(1990, 5, 15)


def test_parse_date_invalid():
    assert parse_birth_date("привет, как дела?") is None


def test_parse_date_impossible_date():
    assert parse_birth_date("31.02.1990") is None


def test_parse_time_colon():
    assert parse_birth_time("14:30") == (14, 30)


def test_parse_time_dot():
    assert parse_birth_time("14.30") == (14, 30)


def test_parse_time_spaces():
    assert parse_birth_time("14 30") == (14, 30)


def test_parse_time_compact():
    assert parse_birth_time("1430") == (14, 30)


def test_parse_time_uhr_with_minutes():
    assert parse_birth_time("14 Uhr 30") == (14, 30)


def test_parse_time_uhr_only_hour():
    assert parse_birth_time("14 Uhr") == (14, 0)


def test_parse_time_hour_only():
    assert parse_birth_time("14") == (14, 0)


def test_parse_time_unknown_russian():
    assert parse_birth_time("не знаю") == "unknown"


def test_parse_time_unknown_german():
    assert parse_birth_time("weiß nicht") == "unknown"


def test_parse_time_invalid():
    assert parse_birth_time("привет") is None


def test_parse_time_out_of_range():
    assert parse_birth_time("25:99") is None
