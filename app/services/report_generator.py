"""
Пайплайн после оплаты (docs/TODO.md п.4): расчёт карты -> текст толкования
от Claude -> PDF -> отправка документа в WhatsApp -> state="report_sent".

Вызывается из двух мест:
- payment_poller.check_pending_payments() — сразу после подтверждения оплаты;
- dialog_manager.handle_message() (ветка state=="paid") — если первая
  попытка упала (Claude/PDF/отправка), любое следующее сообщение
  пользователя запускает генерацию повторно. Так застрявший в "paid"
  диалог чинится без ручного вмешательства.

_GENERATING — примитивная защита от параллельного двойного запуска для
одного номера (поллер и входящее сообщение могут сработать одновременно).
Работает только в пределах одного процесса — при нескольких gunicorn-workers
глобальной защиты нет, но поллер и так должен жить в единственном
экземпляре (см. ENABLE_INPROCESS_PAYMENT_POLLER).
"""
import logging
import os
import threading
from datetime import date

from app.config import Config
from app.models import conversation_state
from app.services import claude_service, evolution_api, natal_chart, pdf_generator

logger = logging.getLogger(__name__)

_GENERATING: set[str] = set()
_GENERATING_LOCK = threading.Lock()

REPORTS_DIR = os.path.join(os.path.dirname(Config.DATABASE_PATH), "reports")


def generate_and_send_report(phone: str) -> bool:
    """
    Полный цикл для одного оплатившего пользователя. Возвращает True при
    успехе. При ошибке пишет пользователю извинение, оставляет state="paid"
    (для повторной попытки при следующем сообщении) и возвращает False.
    """
    with _GENERATING_LOCK:
        if phone in _GENERATING:
            logger.info("Bericht für %s wird bereits generiert — übersprungen.", phone)
            return False
        _GENERATING.add(phone)

    try:
        return _generate_and_send(phone)
    finally:
        with _GENERATING_LOCK:
            _GENERATING.discard(phone)


def _generate_and_send(phone: str) -> bool:
    state = conversation_state.get_or_create(phone)
    if state.get("state") != "paid":
        logger.info("Kein Bericht für %s: Zustand ist '%s', nicht 'paid'.", phone, state.get("state"))
        return False

    try:
        chart = natal_chart.compute(state)

        interpretation = claude_service.generate_interpretation(
            state,
            chart["houses"],
            chart["findings"],
            rin_candidates=chart["rin_candidates"],
            house_activation=chart["house_activation"],
        )

        birth_date_display = date.fromisoformat(state["birth_date"]).strftime("%d.%m.%Y")
        birth_time_display = state["birth_time"]
        if chart["is_time_approximate"]:
            birth_time_display += " (angenommen: 12:00)"

        os.makedirs(REPORTS_DIR, exist_ok=True)
        pdf_path = os.path.join(REPORTS_DIR, f"report_{phone}.pdf")
        pdf_generator.generate_report_pdf(
            pdf_path,
            {
                "date": birth_date_display,
                "time": birth_time_display,
                "place": state["birth_place"],
            },
            chart["houses"],
            chart["findings"],
            interpretation,
        )

        evolution_api.send_document(
            phone,
            pdf_path,
            "Lal-Kitab-Auswertung.pdf",
            caption="Hier ist deine persönliche Lal-Kitab-Auswertung. 🌙",
        )
    except Exception:
        logger.exception("Berichts-Pipeline fehlgeschlagen für %s", phone)
        try:
            evolution_api.send_text(
                phone,
                "Bei der Erstellung deines Berichts ist leider ein Fehler "
                "aufgetreten. Keine Sorge — deine Zahlung ist registriert. "
                "Schreib mir einfach eine beliebige Nachricht, dann versuche "
                "ich es sofort noch einmal.",
            )
        except Exception:
            logger.exception("Fehlerbenachrichtigung an %s fehlgeschlagen", phone)
        return False

    conversation_state.update(phone, state="report_sent")
    logger.info("Bericht erfolgreich an %s gesendet.", phone)
    return True
