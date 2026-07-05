"""
Джьотиш / Vimshottari Dasha — доступ к трактовкам эффектов Антардаш,
оцифрованным в docs/jyotish_dasha_effects.yaml (см. заголовок того файла
про источник, статус и почему это НЕ дословная копия BPHS). Сам расчёт
периодов (Махадаша/Антардаша) — app/services/dasha.py; этот модуль
отвечает только за поиск готовой трактовки по паре владык.
"""
import os
from dataclasses import dataclass, field
from typing import List

import yaml

RULES_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "jyotish_dasha_effects.yaml")


@dataclass
class DashaEffect:
    rule_id: str
    mahadasha_lord: str
    antardasha_lord: str
    summary: str
    severity: str  # "positive" | "caution" | "mixed"
    benefit_effects: List[dict] = field(default_factory=list)
    malefic_effects: List[dict] = field(default_factory=list)
    remedy: str | None = None


def load_rules(path: str = RULES_PATH) -> List[dict]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or []


def get_dasha_effect(mahadasha_lord: str, antardasha_lord: str) -> DashaEffect | None:
    """
    Direkter Lookup einer Antardasha-Regel (Mahadasha-Herr + Antardasha-Herr)
    aus docs/jyotish_dasha_effects.yaml — analog zu lal_kitab.get_rule().
    """
    for rule in load_rules():
        if rule["mahadasha_lord"] == mahadasha_lord and rule["antardasha_lord"] == antardasha_lord:
            return DashaEffect(
                rule_id=rule["id"],
                mahadasha_lord=rule["mahadasha_lord"],
                antardasha_lord=rule["antardasha_lord"],
                summary=rule["summary"].strip(),
                severity=rule["severity"],
                benefit_effects=rule.get("benefit_effects") or [],
                malefic_effects=rule.get("malefic_effects") or [],
                remedy=rule.get("remedy"),
            )
    return None
