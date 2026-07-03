import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.lal_kitab import (
    analyze,
    load_rules,
    load_rin_debts,
    detect_rin,
    compute_house_activation,
)


def test_rules_load_and_are_well_formed():
    rules = load_rules()
    assert len(rules) > 0
    for rule in rules:
        assert rule["planet"]
        assert 1 <= rule["house"] <= 12
        assert rule["severity"] in ("positive", "caution", "neutral", "mixed")
        assert rule["summary"].strip()


def test_analyze_matches_planet_in_house():
    houses = {"Jupiter": {"sign": "Leo", "house": 1}}
    findings = analyze(houses)
    assert len(findings) == 1
    assert findings[0].rule_id == "jupiter_house_1"
    assert findings[0].title == "Jupiter in House 1"
    assert len(findings[0].benefit_effects) > 0
    assert len(findings[0].malefic_effects) > 0


def test_analyze_no_match_for_empty_chart():
    findings = analyze({})
    assert findings == []


def test_analyze_no_match_for_wrong_house():
    houses = {"Jupiter": {"sign": "Cancer", "house": 4}}
    findings = analyze(houses)
    assert all(f.house == 4 for f in findings)
    assert any(f.rule_id == "jupiter_house_4" for f in findings)


def test_rin_debts_load_and_are_well_formed():
    debts = load_rin_debts()
    assert len(debts) == 9
    for debt in debts:
        assert debt["planet"]
        assert debt["debt_type"]
        assert debt["cause"].strip()
        assert debt["symptoms"].strip()
        assert debt["remedy"].strip()


def test_detect_rin_matches_planet_in_house_any():
    houses = {"Jupiter": {"sign": "Sagittarius", "house": 9}}
    findings = detect_rin(houses)
    assert len(findings) == 1
    assert findings[0].debt_id == "father_debt_jupiter"
    assert findings[0].confidence == "low"


def test_detect_rin_no_match_outside_house_any():
    houses = {"Jupiter": {"sign": "Leo", "house": 1}}
    findings = detect_rin(houses)
    assert findings == []


def test_detect_rin_skips_debts_with_missing_house_data():
    # mother_debt_moon has house_any: null (data gap) — must never match.
    houses = {"Moon": {"sign": "Cancer", "house": house} for house in range(1, 13)}
    findings = detect_rin(houses)
    assert all(f.debt_id != "mother_debt_moon" for f in findings)


def test_compute_house_activation_covers_all_houses():
    houses = {"Jupiter": {"sign": "Leo", "house": 1}}
    activation = compute_house_activation(houses)
    assert set(activation.keys()) == set(range(1, 13))
    assert activation[1]["occupied"] is True
    assert activation[2]["occupied"] is False
    assert activation[9]["awakening_planet"] == "Jupiter"
    assert activation[9]["awakening_planet_house"] == 1


def test_compute_house_activation_side_dormancy():
    # All planets bunched in the latter side (7-12) -> prior side (1-6) is
    # empty, so per the source rule the LATTER side (7-12) is deemed dormant.
    houses = {
        "Jupiter": {"house": 7}, "Sun": {"house": 8}, "Moon": {"house": 9},
        "Mars": {"house": 10}, "Mercury": {"house": 11}, "Venus": {"house": 12},
        "Saturn": {"house": 7}, "Rahu": {"house": 8}, "Ketu": {"house": 9},
    }
    activation = compute_house_activation(houses)
    assert all(activation[h]["side_dormant"] for h in range(7, 13))
    assert all(not activation[h]["side_dormant"] for h in range(1, 7))
