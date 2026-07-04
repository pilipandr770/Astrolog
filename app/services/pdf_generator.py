"""
Рендер PDF-отчёта. WeasyPrint конвертирует HTML+CSS в PDF — проще всего
делать красивую вёрстку, дизайн полностью через CSS в шаблоне.

Тело отчёта (интерпретация) приходит от Claude в Markdown и конвертируется
здесь в HTML — Claude пишет ВЕСЬ текст (заголовки, таблицу позиций,
секцию про календарь) на языке клиента, поэтому в шаблоне почти нет
статических надписей (см. обсуждение "смесь трёх языков" в чате).
"""
import os

import markdown
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

# Языконезависимые аббревиатуры для ячеек календарной сетки; их расшифровку
# на языке клиента пишет Claude в последней секции интерпретации (см.
# claude_service._calendar_section).
PLANET_ABBR = {
    "Sun": "Su",
    "Moon": "Mo",
    "Mars": "Ma",
    "Mercury": "Me",
    "Jupiter": "Ju",
    "Venus": "Ve",
    "Saturn": "Sa",
    "Rahu": "Ra",
    "Ketu": "Ke",
}


def generate_report_pdf(
    output_path: str,
    birth_data: dict,
    houses: dict,
    findings: list,
    interpretation_text: str,
    calendar: list | None = None,
):
    """
    houses/findings остаются в сигнатуре для совместимости, но в шаблоне
    больше не отображаются напрямую: сырые правила были на английском и
    дублировали интерпретацию (см. ревью первого реального отчёта) —
    теперь всё их содержимое доносит текст Claude.
    """
    template = env.get_template("report.html")
    interpretation_html = markdown.markdown(interpretation_text, extensions=["tables"])
    html_content = template.render(
        birth_data=birth_data,
        interpretation_html=interpretation_html,
        calendar=calendar,
        planet_abbr=PLANET_ABBR,
    )
    HTML(string=html_content).write_pdf(output_path)
    return output_path
