"""
Правила Лал Китаб (Lal Kitab) — это НЕ то же самое, что классическая
джйотиш-интерпретация. Ключевые специфичные для Лал Китаб концепции:

1. Rin (Долги) — кармические "долги" по определённым комбинациям планет
   в определённых домах (Pitra Rin, Matri Rin, Stri Rin и т.д.) — данные
   в docs/lal_kitab_rin.yaml. detect_rin() ниже — НИЗКОЙ уверенности
   детектор (см. её docstring и docs/LAL_KITAB_NOTES.md почему).
2. "Спящие" и "пробуждённые" дома (sleeping/awakened houses) — не все дома
   активны одинаково, это зависит от расположения планет.
   compute_house_activation() ниже считает это по чётко описанным в
   первоисточнике правилам (таблица "дом → пробуждающая планета" +
   правило "пустая половина карты").
3. Влияние соседних домов — характерная черта именно Лал Китаб-подхода.
4. Ежегодные "хиты" (Varshphal) по Лал Китаб — здесь не реализовано.
5. Простые ремедии (upay) — бытовые действия вместо мантр/янтр.

Источник правил и обоснование формата — см. docs/LAL_KITAB_NOTES.md.
Сами правила — docs/lal_kitab_rules.yaml (по планете + дому — все 9
планет/узлов × 12 домов заполнены, 108 правил).

НЕ выдавай пользователю результат этого модуля как есть, пока правила
не наполнены и не сверены с первоисточником (или несколькими независимыми
источниками) — риск давать неверные "кармические" утверждения от лица бота.
"""

import os
from dataclasses import dataclass, field
from typing import List

import yaml

RULES_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "lal_kitab_rules.yaml")
RIN_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "lal_kitab_rin.yaml")

# Каждый дом "пробуждается" либо занимающей его планетой, либо (если дом
# пуст) присутствием где-либо в карте своей "пробуждающей" планеты из этой
# таблицы. Источник: Goswami 1952, "12 Fixed Houses" / "Dormant Fixed
# Houses", gosvami_1952.txt ~строки 10295-10420.
HOUSE_AWAKENING_PLANET = {
    1: "Mars",
    2: "Moon",
    3: "Mercury",
    4: "Moon",
    5: "Sun",
    6: "Rahu",
    7: "Venus",
    8: "Moon",
    9: "Jupiter",
    10: "Saturn",
    11: "Jupiter",
    12: "Ketu",
}

# Дома 1-6 ("prior side"), 7-12 ("latter side"): если на одной половине
# карты вообще нет планет, вся ПРОТИВОПОЛОЖНАЯ половина считается "спящей"
# целиком (там же, несколькими абзацами ниже).
PRIOR_SIDE_HOUSES = range(1, 7)
LATTER_SIDE_HOUSES = range(7, 13)

# Возраст/жизненное событие, после которого спящая планета "просыпается"
# сама по себе (там же, таблица "When would a Dormant Planet become Active
# on Its Own"). Используется только как справочные данные для Claude —
# полноценный расчёт текущего возраста пользователя пока не подключён.
PLANET_SELF_AWAKENING = {
    "Jupiter": {"event": "starting one's own business", "after_age": 16},
    "Sun": {"event": "government service or a link with government", "after_age": 22},
    "Moon": {"event": "education", "after_age": 24},
    "Venus": {"event": "marriage", "after_age": 25},
    "Mars": {"event": "a relationship with a woman", "after_age": 28},
    "Mercury": {"event": "business, or a sister's/daughter's marriage", "after_age": 34},
    "Saturn": {"event": "a relationship tied to property/house", "after_age": 36},
    "Rahu": {"event": "a relationship with in-laws", "after_age": 42},
    "Ketu": {"event": "the birth of offspring", "after_age": 48},
}


@dataclass
class LalKitabFinding:
    rule_id: str
    planet: str
    house: int
    title: str
    summary: str
    severity: str  # "positive" | "caution" | "neutral" | "mixed"
    benefit_effects: List[dict] = field(default_factory=list)
    malefic_effects: List[dict] = field(default_factory=list)
    remedy: str | None = None
    source: str | None = None


@dataclass
class RinFinding:
    debt_id: str
    planet: str
    debt_type: str
    cause: str
    symptoms: str
    remedy: str
    confidence: str  # всегда "low" — см. detect_rin()
    source: str | None = None


def load_rules(path: str = RULES_PATH) -> List[dict]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def load_rin_debts(path: str = RIN_PATH) -> List[dict]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("debts") or []


def get_rule(planet: str, house: int) -> dict | None:
    """
    Direkter Lookup einer einzelnen Regel (planet+house) aus
    docs/lal_kitab_rules.yaml — für app/services/transit_forecast.py, das
    Regeln für viele Planet/Haus-Kombinationen abfragt, ohne jedes Mal
    einen vollen Chart über analyze() aufzubauen.
    """
    for rule in load_rules():
        if rule["planet"] == planet and rule["house"] == house:
            return rule
    return None


def analyze(houses: dict) -> List[LalKitabFinding]:
    """
    Прогоняет расчёты по правилам Лал Китаб и возвращает список находок.

    houses — результат app.services.ephemeris.assign_houses()

    Совпадение проверяется только по базовому условию "планета в доме"
    (это единственное, что можно сопоставить программно без данных об
    экзальтации/аспектах, которых ephemeris.py пока не считает). Полные
    списки benefit_effects/malefic_effects передаются в claude_service —
    выбор того, какие из текстовых условий применимы к конкретной карте,
    делает Claude, видя все позиции планет и домов целиком. Подробнее и
    почему так — см. docs/LAL_KITAB_NOTES.md.
    """
    rules = load_rules()
    findings = []
    for rule in rules:
        planet_data = houses.get(rule["planet"])
        if planet_data is None or planet_data.get("house") != rule["house"]:
            continue
        findings.append(
            LalKitabFinding(
                rule_id=rule["id"],
                planet=rule["planet"],
                house=rule["house"],
                title=f"{rule['planet']} in House {rule['house']}",
                summary=rule["summary"].strip(),
                severity=rule["severity"],
                benefit_effects=rule.get("benefit_effects") or [],
                malefic_effects=rule.get("malefic_effects") or [],
                remedy=rule.get("remedy"),
                source=rule.get("source"),
            )
        )
    return findings


def detect_rin(houses: dict) -> List[RinFinding]:
    """
    Детектор кармических долгов (Rin) — НИЗКОЙ уверенности.

    docs/lal_kitab_rin.yaml даёт для каждого вида долга упрощённые условия
    "планета в одном из house_any" + "хотя бы одна из enemy_planets
    присутствует в карте" — но реальное правило первоисточника требует,
    чтобы вражеская планета стояла "в корне" конкретного дома-пары (см.
    таблицы "First/Second Degree Debt to Father" в
    gosvami_1952.txt ~строки 12680-12730), а не просто где-то в карте.
    Поскольку в натальной карте всегда присутствуют все 9 планет/узлов,
    проверка "enemy planet есть в карте" тривиально верна почти всегда —
    поэтому она НЕ используется здесь как условие срабатывания, а служит
    только для ранжирования (сколько врагов из списка вообще на своих
    местах не играет роли, пока точные пары домов не подтверждены).

    Из-за этого функция возвращает только "планета в доме house_any" как
    кандидата на долг, с confidence="low", и НЕ должна показываться
    пользователю как утверждение — только как сигнал Claude, который сам
    должен трактовать это очень осторожно (см. промпт в claude_service.py)
    или как повод для ручной сверки перед продакшеном.
    """
    debts = load_rin_debts()
    findings = []
    for debt in debts:
        house_any = debt.get("house_any")
        if not house_any:
            continue  # пробел в данных (см. lal_kitab_rin.yaml) — пропускаем
        planet_data = houses.get(debt["planet"])
        if planet_data is None or planet_data.get("house") not in house_any:
            continue
        findings.append(
            RinFinding(
                debt_id=debt["id"],
                planet=debt["planet"],
                debt_type=debt["debt_type"],
                cause=debt["cause"].strip(),
                symptoms=debt["symptoms"].strip(),
                remedy=debt["remedy"].strip(),
                confidence="low",
                source=debt.get("source"),
            )
        )
    return findings


def compute_house_activation(houses: dict) -> dict:
    """
    Для каждого из 12 домов определяет: занят ли он планетой, и если нет —
    какая планета могла бы его "пробудить" и стоит ли эта планета вообще
    где-то в карте. Также помечает, не "спит" ли целиком половина карты
    (1-6 или 7-12) из-за полного отсутствия планет на противоположной
    половине. Правила — см. HOUSE_AWAKENING_PLANET и комментарий выше.

    Возвращает {house_no: {occupied, side_dormant, awakening_planet,
    awakening_planet_house}} — сырые сигналы для claude_service, а не
    готовый вердикт "активен/не активен" (сочетание "спящий дом, но
    пробуждающая планета сильна" и т.п. — на усмотрение Claude, видящего
    полную карту).
    """
    occupied_houses = {data["house"] for data in houses.values() if "house" in data}
    prior_occupied = any(h in PRIOR_SIDE_HOUSES for h in occupied_houses)
    latter_occupied = any(h in LATTER_SIDE_HOUSES for h in occupied_houses)

    activation = {}
    for house_no in range(1, 13):
        awakening_planet = HOUSE_AWAKENING_PLANET[house_no]
        awakening_planet_data = houses.get(awakening_planet)
        side_dormant = (
            not prior_occupied if house_no in LATTER_SIDE_HOUSES
            else not latter_occupied if house_no in PRIOR_SIDE_HOUSES
            else False
        )
        activation[house_no] = {
            "occupied": house_no in occupied_houses,
            "side_dormant": side_dormant,
            "awakening_planet": awakening_planet,
            "awakening_planet_house": awakening_planet_data.get("house") if awakening_planet_data else None,
        }
    return activation
