import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import jyotish


def test_load_rules_returns_81_entries():
    rules = jyotish.load_rules()
    assert len(rules) == 81


def test_get_dasha_effect_returns_matching_rule():
    effect = jyotish.get_dasha_effect("Sun", "Moon")
    assert effect is not None
    assert effect.rule_id == "dasha_sun_moon"
    assert effect.mahadasha_lord == "Sun"
    assert effect.antardasha_lord == "Moon"
    assert effect.severity in ("positive", "caution", "mixed")
    assert isinstance(effect.benefit_effects, list)
    assert isinstance(effect.malefic_effects, list)


def test_get_dasha_effect_returns_none_for_unknown_pair():
    assert jyotish.get_dasha_effect("NotAPlanet", "AlsoNot") is None


def test_all_81_combinations_are_present():
    lords = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
    for maha in lords:
        for antar in lords:
            assert jyotish.get_dasha_effect(maha, antar) is not None, f"{maha}-{antar} missing"
