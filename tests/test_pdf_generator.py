import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date

from app.services import pdf_generator


def _fake_calendar(days=3):
    calendar = []
    severities = ["positive", "caution", "mixed", "neutral"]
    for day_offset in range(days):
        blocks = []
        for block_index in range(12):
            blocks.append({
                "start_hour": block_index * 2,
                "end_hour": block_index * 2 + 2,
                "lagna_house": (block_index % 12) + 1,
                "content": {
                    "source": "transit" if block_index == 3 else "natal",
                    "planet": "Jupiter",
                    "rule": {"summary": "x", "severity": severities[block_index % 4]},
                } if block_index != 5 else None,  # ein leerer Block pro Tag
            })
        calendar.append({
            "date": date(2026, 7, 10 + day_offset),
            "slow_transits": {},
            "blocks": blocks,
        })
    return calendar


MARKDOWN_TEXT = """# Твоя карта

| Планета | Знак | Дом |
|---|---|---|
| Юпитер | Рыбы | 1 |

## Раздел

Немного **жирного** текста и *курсива*.

---

Список:
- раз
- два
"""


def test_generate_report_pdf_renders_markdown_and_calendar(tmp_path):
    output = str(tmp_path / "report.pdf")
    result = pdf_generator.generate_report_pdf(
        output,
        {"date": "15.05.1990", "time": "14:30", "place": "Berlin, Deutschland"},
        {"Moon": {"sign": "Cancer", "house": 4}},
        [],
        MARKDOWN_TEXT,
        calendar=_fake_calendar(),
    )
    assert os.path.exists(result)
    assert os.path.getsize(result) > 1000  # echtes PDF, kein leeres Artefakt


def test_generate_report_pdf_without_calendar(tmp_path):
    output = str(tmp_path / "report_no_cal.pdf")
    pdf_generator.generate_report_pdf(
        output,
        {"date": "15.05.1990", "time": "14:30", "place": "Berlin"},
        {},
        [],
        "## Nur Text\n\nOhne Kalender.",
    )
    assert os.path.getsize(output) > 500
