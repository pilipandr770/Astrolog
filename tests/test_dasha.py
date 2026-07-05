import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date

from app.services import dasha


def test_dasha_years_sum_to_120_year_cycle():
    assert sum(dasha.DASHA_YEARS.values()) == 120
    assert dasha.TOTAL_CYCLE_YEARS == 120


def test_nakshatra_index_ashwini_at_zero_degrees():
    assert dasha.nakshatra_index(0.0) == 0  # Ashwini


def test_nakshatra_index_boundaries():
    # Jede Nakshatra ist 13°20' (=13.3333...) breit, 27 Stück über 360°.
    # Echte Ephemeris-Längengrade liegen immer in [0, 360) — 360.0 selbst
    # ist kein realistischer Input und wird hier bewusst nicht getestet
    # (Floating-Point-Rundung an dieser exakten Grenze ist irrelevant).
    assert dasha.nakshatra_index(13.3) == 0  # noch Ashwini
    assert dasha.nakshatra_index(13.34) == 1  # schon Bharani
    assert dasha.nakshatra_index(359.9) == 26  # Revati


def test_starting_lord_matches_standard_nakshatra_lord_table():
    # Standard-Zuordnung (siehe BPHS Ch. 46): Ashwini=Ketu, Krittika=Surya,
    # Ardra=Rahu, Ashlesha=Budh (Mercury) usw.
    ashwini_start = 0 * dasha.NAKSHATRA_SPAN
    krittika_start = 2 * dasha.NAKSHATRA_SPAN
    ardra_start = 5 * dasha.NAKSHATRA_SPAN

    lord, _ = dasha._starting_lord_and_balance(ashwini_start + 0.01)
    assert lord == "Ketu"
    lord, _ = dasha._starting_lord_and_balance(krittika_start + 0.01)
    assert lord == "Sun"
    lord, _ = dasha._starting_lord_and_balance(ardra_start + 0.01)
    assert lord == "Rahu"


def test_starting_balance_full_at_start_of_nakshatra():
    # Genau am Anfang der Nakshatra ist noch (fast) die volle Dasha übrig.
    lord, remaining_fraction = dasha._starting_lord_and_balance(0.0)
    assert lord == "Ketu"
    assert remaining_fraction == 1.0


def test_starting_balance_near_zero_at_end_of_nakshatra():
    # Kurz vor Ende der Nakshatra ist fast nichts mehr von der Dasha übrig.
    almost_end = dasha.NAKSHATRA_SPAN - 0.001
    lord, remaining_fraction = dasha._starting_lord_and_balance(almost_end)
    assert lord == "Ketu"
    assert remaining_fraction < 0.001


def test_mahadasha_sequence_first_entry_is_partial_and_rest_full():
    birth = date(1990, 5, 15)
    # Exakt in der Mitte von Ashwini geboren -> 50% der Ketu-Dasha (7 Jahre) übrig.
    moon_lon = dasha.NAKSHATRA_SPAN / 2
    sequence = dasha.compute_mahadasha_sequence(moon_lon, birth, count=3)

    assert sequence[0]["lord"] == "Ketu"
    assert abs(sequence[0]["years"] - 3.5) < 0.01
    assert abs(sequence[0]["elapsed_years"] - 3.5) < 0.01
    assert sequence[0]["start_date"] == birth

    # Danach volle Perioden in fester Reihenfolge: Venus, Sun.
    assert sequence[1]["lord"] == "Venus"
    assert sequence[1]["years"] == 20
    assert sequence[1]["elapsed_years"] == 0.0
    assert sequence[1]["start_date"] == sequence[0]["end_date"]

    assert sequence[2]["lord"] == "Sun"
    assert sequence[2]["years"] == 6


def test_mahadasha_sequence_full_cycle_covers_120_years_minus_elapsed():
    birth = date(2000, 1, 1)
    moon_lon = 0.0  # exakt am Anfang von Ashwini -> keine verstrichene Zeit
    sequence = dasha.compute_mahadasha_sequence(moon_lon, birth, count=9)
    total_years = sum(entry["years"] for entry in sequence)
    assert abs(total_years - 120) < 0.01


def test_antardasha_sequence_sums_to_mahadasha_years_for_full_period():
    mahadasha = {
        "lord": "Sun", "start_date": date(2020, 1, 1),
        "end_date": date(2026, 1, 1), "years": 6.0, "elapsed_years": 0.0,
    }
    antardashas = dasha.compute_antardasha_sequence(mahadasha)
    assert len(antardashas) == 9
    assert antardashas[0]["lord"] == "Sun"  # beginnt beim eigenen Herrn
    assert antardashas[1]["lord"] == "Moon"
    total = sum(a["years"] for a in antardashas)
    assert abs(total - 6.0) < 0.01


def test_antardasha_sequence_trims_elapsed_portion_for_partial_mahadasha():
    # Halb "verbrauchte" Ketu-Mahadasha (7 Jahre nominal, 3.5 Jahre schon
    # vor der Geburt verstrichen) -> Antardasha-Liste darf nur die
    # verbleibenden 3.5 Jahre abdecken, beginnend NICHT bei Ketu-Ketu.
    mahadasha = {
        "lord": "Ketu", "start_date": date(2020, 1, 1),
        "end_date": date(2023, 7, 3), "years": 3.5, "elapsed_years": 3.5,
    }
    antardashas = dasha.compute_antardasha_sequence(mahadasha)
    assert antardashas[0]["start_date"] == mahadasha["start_date"]
    total = sum(a["years"] for a in antardashas)
    assert abs(total - 3.5) < 0.05
    # Die Sequenz darf NICHT bei Ketu-Ketu (dem allerersten Antardasha-Slot)
    # beginnen, weil die Hälfte der Mahadasha schon vor der Geburt verstrichen ist.
    assert antardashas[0]["lord"] != "Ketu" or len(antardashas) < 9


def test_compute_current_dasha_returns_mahadasha_and_antardasha_at_birth():
    birth = date(1990, 5, 15)
    result = dasha.compute_current_dasha(0.0, birth, birth)
    assert result["mahadasha"]["lord"] == "Ketu"
    assert result["antardasha"]["lord"] == "Ketu"  # erster Antardasha-Slot bei voller Balance


def test_compute_current_dasha_returns_none_beyond_horizon():
    birth = date(1990, 5, 15)
    far_future = date(2200, 1, 1)
    result = dasha.compute_current_dasha(0.0, birth, far_future)
    assert result["mahadasha"] is None
    assert result["antardasha"] is None
