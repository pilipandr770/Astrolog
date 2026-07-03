"""
Рендер PDF-отчёта. WeasyPrint конвертирует HTML+CSS в PDF — проще всего
делать красивую вёрстку, дизайн полностью через CSS в шаблоне.
"""
import os
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))


def generate_report_pdf(output_path: str, birth_data: dict, houses: dict, findings: list, interpretation_text: str):
    template = env.get_template("report.html")
    html_content = template.render(
        birth_data=birth_data,
        houses=houses,
        findings=findings,
        interpretation_text=interpretation_text,
    )
    HTML(string=html_content).write_pdf(output_path)
    return output_path
