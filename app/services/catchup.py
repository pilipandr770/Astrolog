"""
Nachhol-Sync für verpasste Nachrichten (siehe Chat-Diskussion): wenn die
WhatsApp-Verbindung (Evolution/Baileys) zwischenzeitlich getrennt war, kann
ein Live-Webhook für eine in dieser Zeit eingegangene Nachricht verloren
gehen — Evolution synchronisiert die Nachricht zwar nachträglich in seine
eigene Chat-Historie, feuert aber KEIN Webhook-Event mehr dafür. Dieses
Modul vergleicht Evolution's Chat-Historie gegen
conversation_state.last_processed_message_ts pro Telefonnummer und lässt
den Bot alle noch unbeantworteten Eingangsnachrichten nachträglich
verarbeiten — auch mit Verzögerung, ganz normal über dialog_manager.handle_message.

Ausgelöst wird das über app/routes/webhook.py bei einem CONNECTION_UPDATE-
Event mit state="open" (siehe run_after_reconnect()) — bewusst NICHT
periodisch, sondern nur beim tatsächlichen (Wieder-)Verbinden.
"""
import logging
import threading
import time

from app.config import Config
from app.models import conversation_state
from app.services import dialog_manager, evolution_api

logger = logging.getLogger(__name__)

_last_run_at = 0.0
_run_lock = threading.Lock()


def _is_group_chat(remote_jid: str) -> bool:
    return remote_jid.endswith("@g.us")


def _chat_has_pending_message(chat: dict) -> bool:
    """
    Billige Vorab-Prüfung anhand von chat.lastMessage, BEVOR die volle
    Nachrichten-Historie dieses Chats geladen wird (spart bei vielen Chats
    unnötige API-Calls): wenn die letzte Nachricht im Chat von UNS kam,
    kann es keine unbeantwortete Eingangsnachricht geben.
    """
    last_message = chat.get("lastMessage")
    if not last_message:
        return False
    key = last_message.get("key") or {}
    return not key.get("fromMe")


def _catch_up_chat(remote_jid: str) -> None:
    try:
        records = evolution_api.find_messages(remote_jid, limit=50)
    except Exception:
        logger.exception("Nachhol-Sync: Nachrichten für %s konnten nicht geladen werden", remote_jid)
        return

    # Chronologisch aufsteigend (älteste zuerst) — der Dialog ist eine
    # State machine, Reihenfolge ist wichtig, falls mehrere Nachrichten in
    # der Downtime eingegangen sind (z.B. Datum, dann Uhrzeit, dann Ort).
    records.sort(key=lambda r: r.get("messageTimestamp") or 0)

    for record in records:
        key = record.get("key") or {}
        if key.get("fromMe"):
            continue

        synthetic_payload = {
            "data": {
                "key": key,
                "message": record.get("message"),
                "messageTimestamp": record.get("messageTimestamp"),
            }
        }
        message = evolution_api.extract_incoming_message(synthetic_payload)
        if message is None:
            continue

        phone = message["phone"]
        state = conversation_state.get_or_create(phone)
        last_ts = state.get("last_processed_message_ts") or 0
        ts = message.get("timestamp") or 0
        if ts <= last_ts:
            continue  # bereits verarbeitet (live oder in einem früheren Sync-Lauf)

        logger.info(
            "Nachhol-Sync: verarbeite verpasste Nachricht von %s (ts=%s, id=%s)",
            phone, ts, message.get("message_id"),
        )
        try:
            dialog_manager.handle_message(phone, message)
        except Exception:
            logger.exception("Nachhol-Sync: Verarbeitung für %s (ts=%s) fehlgeschlagen", phone, ts)
            # Nicht weiter versuchen für DIESEN Chat in diesem Lauf — die
            # State machine könnte sonst außer der Reihe fortgesetzt werden.
            return


def check_missed_messages() -> None:
    """Ein vollständiger Nachhol-Sync-Durchlauf über alle Chats der Instanz."""
    try:
        chats = evolution_api.find_chats()
    except Exception:
        logger.exception("Nachhol-Sync: Chat-Liste konnte nicht geladen werden")
        return

    checked = 0
    for chat in chats:
        remote_jid = chat.get("remoteJid") or ""
        if not remote_jid or _is_group_chat(remote_jid):
            continue
        if not _chat_has_pending_message(chat):
            continue
        checked += 1
        try:
            _catch_up_chat(remote_jid)
        except Exception:
            logger.exception("Nachhol-Sync für %s fehlgeschlagen", remote_jid)

    logger.info("Nachhol-Sync abgeschlossen — %s Chat(s) mit möglichen offenen Nachrichten geprüft.", checked)


def run_after_reconnect() -> None:
    """
    Von app/routes/webhook.py bei CONNECTION_UPDATE (state="open") aufgerufen.
    Läuft in einem Hintergrund-Thread, damit die Webhook-Antwort an Evolution
    nicht blockiert wird, und ist per Cooldown (CATCHUP_MIN_INTERVAL_SECONDS)
    gegen mehrere CONNECTION_UPDATE-Events kurz hintereinander (flatternde
    Verbindung) abgesichert.
    """
    if not Config.ENABLE_CATCHUP_SYNC:
        return

    global _last_run_at
    with _run_lock:
        now = time.monotonic()
        if now - _last_run_at < Config.CATCHUP_MIN_INTERVAL_SECONDS:
            logger.info("Nachhol-Sync übersprungen (Cooldown, letzter Lauf vor %.0fs).", now - _last_run_at)
            return
        _last_run_at = now

    def _run():
        logger.info("Nachhol-Sync gestartet (CONNECTION_UPDATE -> open).")
        try:
            check_missed_messages()
        except Exception:
            logger.exception("Nachhol-Sync-Durchlauf fehlgeschlagen")

    threading.Thread(target=_run, daemon=True).start()
