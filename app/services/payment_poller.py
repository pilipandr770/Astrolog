"""
Opt-in Ersatz für den Stripe-Webhook: der Bot läuft auf einer VPS ohne
öffentlich erreichbare HTTPS-Domain, daher kann Stripe keinen Webhook-Push
zustellen. Stattdessen fragt dieses Modul periodisch für jeden Chat im
Status awaiting_payment den Zahlungsstatus seiner Checkout-Session ab.

Nachteil gegenüber einem Webhook: die Bestätigung verzögert sich um bis zu
Config.PAYMENT_POLL_INTERVAL_SECONDS statt sofort zu kommen. Vorteil: keine
öffentliche Erreichbarkeit, kein Domain/Tunnel/offener Port nötig.

WICHTIG bei gunicorn mit mehreren Workern: jeder Worker-Prozess, der
start_background_poller() aufruft, startet einen eigenen Thread — das
würde denselben Chat mehrfach anschreiben. Siehe Config.ENABLE_INPROCESS_PAYMENT_POLLER
und den `python -m app.services.payment_poller`-Einstiegspunkt unten für
den Fall, dass der Poller als eigener, einzelner Prozess laufen soll.
"""
import logging
import threading
import time

from app.config import Config
from app.models import conversation_state
from app.services import evolution_api, report_generator, stripe_service

logger = logging.getLogger(__name__)


def check_pending_payments() -> None:
    for convo in conversation_state.find_awaiting_payment():
        phone = convo["phone"]
        session_id = convo["stripe_session_id"]
        try:
            status = stripe_service.get_payment_status(session_id)
        except Exception:
            logger.exception("Stripe-Statusabfrage fehlgeschlagen für %s (%s)", phone, session_id)
            continue

        if status != "paid":
            continue

        conversation_state.update(phone, paid=1, state="paid")
        evolution_api.send_text(
            phone,
            "Danke für deine Zahlung! Dein Bericht wird jetzt erstellt "
            "und kommt in wenigen Minuten hier an.",
        )
        # Synchron im Poller-Thread (siehe docs/ARCHITECTURE.md, "Известные
        # ограничения"): kein hartes Timeout wie bei einem Webhook, und bei
        # Fehlern triggert die nächste Nutzernachricht einen Retry (siehe
        # dialog_manager, Zweig state=="paid").
        report_generator.generate_and_send_report(phone)


def run_forever(interval_seconds: int = None) -> None:
    interval = interval_seconds or Config.PAYMENT_POLL_INTERVAL_SECONDS
    while True:
        try:
            check_pending_payments()
        except Exception:
            logger.exception("Fehler beim Payment-Polling-Durchlauf")
        time.sleep(interval)


def start_background_poller() -> None:
    """Für den Single-Worker-Fall (z.B. `python run.py`, gunicorn -w 1)."""
    if not Config.ENABLE_INPROCESS_PAYMENT_POLLER:
        logger.info("In-process Payment-Poller deaktiviert (ENABLE_INPROCESS_PAYMENT_POLLER=false).")
        return
    thread = threading.Thread(target=run_forever, daemon=True)
    thread.start()


if __name__ == "__main__":
    # Eigenständiger Prozess für den Mehr-Worker-Fall, z.B. via systemd:
    # python -m app.services.payment_poller
    logging.basicConfig(level=logging.INFO)
    run_forever()
