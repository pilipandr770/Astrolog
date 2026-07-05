"""
Vimshottari Dasha — расчёт планетных периодов (Махадаша/Антардаша) от
рождения. Стандартный, общеизвестный алгоритм ведической астрологии — сам
МЕТОД расчёта является традиционным общим знанием (используется в любом
ведическом ПО), НЕ специфичен для конкретного перевода источника и не
копирует ничьи авторские формулировки. Сверен по BPHS, Ch. 46 "Dashas of
Grahas" (см. docs/jyotish_source/ — локальная копия, НЕ в git, см.
.gitignore) — используется только как приватный справочник для проверки
корректности алгоритма, не как публикуемый источник.

120-летний цикл, 9 планет-владык. Начальный владыка Махадаши при рождении
определяется НЕ знаком, а НАКШАТРОЙ Луны (27 лунных стоянок по 13°20'
каждая) — накшатра также задаёт, какая доля этой Махадаши уже "истекла"
к моменту рождения (остаток = "баланс Дашы").
"""
from datetime import date, timedelta

NAKSHATRA_SPAN = 360 / 27  # 13°20'

# Стандартный порядок владык Дашы начиная с Ашвини (накшатра #0) = Кету.
# 120-летний цикл: 7+20+6+10+7+18+16+19+17 = 120.
DASHA_ORDER = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
DASHA_YEARS = {
    "Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
    "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17,
}
TOTAL_CYCLE_YEARS = sum(DASHA_YEARS.values())  # 120

# Юлианский средний год — стандарт для расчёта длительности Дашы в днях.
DAYS_PER_YEAR = 365.2425


def nakshatra_index(moon_longitude: float) -> int:
    """0 = Ашвини ... 26 = Ревати."""
    return int(moon_longitude // NAKSHATRA_SPAN) % 27


def _starting_lord_and_balance(moon_longitude: float) -> tuple[str, float]:
    """
    Возвращает (владыка Дашы при рождении, остаток ЭТОЙ Махадаши как доля
    0-1). Доля уже пройденной части накшатры определяет, сколько от
    Махадаши стартового владыки уже "израсходовано" к моменту рождения
    (см. BPHS Ch. 46, шлоки 12-16).
    """
    idx = nakshatra_index(moon_longitude)
    lord = DASHA_ORDER[idx % 9]
    position_in_nakshatra = moon_longitude % NAKSHATRA_SPAN
    elapsed_fraction = position_in_nakshatra / NAKSHATRA_SPAN
    remaining_fraction = 1 - elapsed_fraction
    return lord, remaining_fraction


def compute_mahadasha_sequence(moon_longitude: float, birth_date: date, count: int = 9) -> list[dict]:
    """
    Возвращает последовательность Махадаш от рождения:
    [{"lord", "start_date", "end_date", "years", "elapsed_years"}, ...].

    Первая запись — ЧАСТИЧНЫЙ период (остаток Дашы стартового владыки на
    момент рождения), дальше — полные периоды в фиксированном 9-периодном
    порядке. elapsed_years — сколько от НОМИНАЛЬНОЙ длины этого периода уже
    "прошло" до рождения (0 для всех, кроме первой записи) — нужно для
    corectного расчёта Антардаш внутри частичной первой Махадаши, см.
    compute_antardasha_sequence().

    count — сколько Махадаш вернуть (по умолчанию 9 = один полный
    120-летний цикл от рождения, с запасом на всю жизнь).
    """
    start_lord, remaining_fraction = _starting_lord_and_balance(moon_longitude)
    start_idx = DASHA_ORDER.index(start_lord)

    sequence = []
    cursor_date = birth_date
    for i in range(count):
        lord = DASHA_ORDER[(start_idx + i) % 9]
        full_years = DASHA_YEARS[lord]
        if i == 0:
            years = full_years * remaining_fraction
            elapsed_years = full_years - years
        else:
            years = full_years
            elapsed_years = 0.0
        end_date = cursor_date + timedelta(days=years * DAYS_PER_YEAR)
        sequence.append({
            "lord": lord,
            "start_date": cursor_date,
            "end_date": end_date,
            "years": round(years, 4),
            "elapsed_years": round(elapsed_years, 4),
        })
        cursor_date = end_date
    return sequence


def compute_antardasha_sequence(mahadasha: dict) -> list[dict]:
    """
    Антардаши (под-периоды) внутри ОДНОЙ Махадаши — тот же 9-периодный
    порядок, начиная с владыки самой Махадаши. Длительность каждой
    Антардаши считается от НОМИНАЛЬНОЙ (полной) длины Махадаши:
    antardasha_years = full_mahadasha_years * dasha_years(antar_lord) / 120.

    mahadasha["elapsed_years"] > 0 (только у самой первой, "балансовой"
    Махадаши от рождения) обрезает начало последовательности — рождение
    приходится не на начало первой Антардаши цикла, а где-то внутри
    номинальной последовательности; эта функция возвращает только ту её
    часть, что приходится ПОСЛЕ рождения, начиная ровно с
    mahadasha["start_date"].
    """
    lord = mahadasha["lord"]
    start_idx = DASHA_ORDER.index(lord)
    full_years = DASHA_YEARS[lord]
    elapsed_years = mahadasha.get("elapsed_years", 0.0)

    sequence = []
    cumulative = 0.0
    cursor_date = mahadasha["start_date"]
    for i in range(9):
        antar_lord = DASHA_ORDER[(start_idx + i) % 9]
        nominal_years = full_years * DASHA_YEARS[antar_lord] / TOTAL_CYCLE_YEARS
        segment_start = cumulative
        segment_end = cumulative + nominal_years
        cumulative = segment_end

        if segment_end <= elapsed_years:
            continue  # этот под-период целиком приходится на время ДО рождения

        years_remaining = segment_end - max(segment_start, elapsed_years)
        end_date = cursor_date + timedelta(days=years_remaining * DAYS_PER_YEAR)
        sequence.append({
            "lord": antar_lord,
            "start_date": cursor_date,
            "end_date": end_date,
            "years": round(years_remaining, 4),
        })
        cursor_date = end_date
    return sequence


def _find_at_date(sequence: list[dict], on_date: date) -> dict | None:
    return next((entry for entry in sequence if entry["start_date"] <= on_date < entry["end_date"]), None)


def compute_current_dasha(moon_longitude: float, birth_date: date, on_date: date) -> dict:
    """
    Удобная точка входа: возвращает {"mahadasha": {...}, "antardasha": {...}}
    на указанную дату (обычно "сегодня"). None, если on_date выходит за
    рассчитанный горизонт (по умолчанию compute_mahadasha_sequence — один
    120-летний цикл от рождения, с запасом на всю жизнь).
    """
    mahadasha_sequence = compute_mahadasha_sequence(moon_longitude, birth_date)
    mahadasha = _find_at_date(mahadasha_sequence, on_date)
    if mahadasha is None:
        return {"mahadasha": None, "antardasha": None}

    antardasha_sequence = compute_antardasha_sequence(mahadasha)
    antardasha = _find_at_date(antardasha_sequence, on_date)
    return {"mahadasha": mahadasha, "antardasha": antardasha}


def compute_month_segments(
    moon_longitude: float, birth_date: date, start_date: date, days: int = 30
) -> list[dict]:
    """
    Liefert die Antardasha-Segmente, die das Fenster [start_date,
    start_date+days) überschneiden — für den Jyotish-Monatsbericht (siehe
    report_generator/pdf_generator). Jedes Segment:
    {"start_date", "end_date", "mahadasha_lord", "antardasha_lord"},
    auf das Fenster zugeschnitten (geclippt) — meist nur 1 Segment, da eine
    Antardasha typischerweise deutlich länger als 30 Tage dauert; mehrere
    Segmente nur, wenn ein Antardasha- (oder seltener Mahadasha-)Wechsel
    genau in diesen Zeitraum fällt.
    """
    window_end = start_date + timedelta(days=days)
    mahadasha_sequence = compute_mahadasha_sequence(moon_longitude, birth_date, count=9)

    segments = []
    for mahadasha in mahadasha_sequence:
        if mahadasha["end_date"] <= start_date or mahadasha["start_date"] >= window_end:
            continue  # dieser Mahadasha-Zeitraum liegt komplett außerhalb des Fensters
        for antardasha in compute_antardasha_sequence(mahadasha):
            if antardasha["end_date"] <= start_date or antardasha["start_date"] >= window_end:
                continue
            segments.append({
                "start_date": max(antardasha["start_date"], start_date),
                "end_date": min(antardasha["end_date"], window_end),
                "mahadasha_lord": mahadasha["lord"],
                "antardasha_lord": antardasha["lord"],
            })
    return segments
