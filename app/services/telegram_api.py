"""
Telegram-Client — dupliziert das WhatsApp-Interface (evolution_api.py) als
zweiten Kanal für denselben Bot (siehe Chat-Diskussion "Telegram als
Duplikat-Interface"). Kontakte werden über eine eigene, mit "tg:"
präfixte ID identifiziert (siehe app/services/messaging.py) — bewusst
KEINE Verknüpfung mit WhatsApp-Telefonnummern; Telegram-Kunden bekommen
einen eigenen, unabhängigen conversation_state-Datensatz.
"""
import logging

import requests
from app.config import Config
from app.services.evolution_api import _split_text

logger = logging.getLogger(__name__)

BASE_URL = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}"
FILE_BASE_URL = f"https://api.telegram.org/file/bot{Config.TELEGRAM_BOT_TOKEN}"

# Telegram erlaubt bis zu 4096 Zeichen pro Nachricht — dieselbe Chunking-
# Logik wie bei WhatsApp (_split_text aus evolution_api) reicht dafür aus,
# das WhatsApp-Limit (3500) liegt ohnehin darunter.
MAX_TEXT_LENGTH = 4096


def send_text(chat_id: str, text: str) -> list[dict]:
    """Sendet Text an Telegram. Lange Texte werden wie bei WhatsApp aufgeteilt."""
    url = f"{BASE_URL}/sendMessage"
    responses = []
    for chunk in _split_text(text, max_length=MAX_TEXT_LENGTH):
        payload = {"chat_id": chat_id, "text": chunk}
        response = requests.post(url, json=payload, timeout=20)
        response.raise_for_status()
        responses.append(response.json())
    return responses


def send_document(chat_id: str, file_path: str, filename: str, caption: str = "") -> dict:
    url = f"{BASE_URL}/sendDocument"
    with open(file_path, "rb") as f:
        files = {"document": (filename, f, "application/pdf")}
        data = {"chat_id": chat_id, "caption": caption}
        response = requests.post(url, data=data, files=files, timeout=60)
    response.raise_for_status()
    return response.json()


def get_file_download_url(file_id: str) -> str:
    """
    Telegram-Mediendateien sind (anders als WhatsApp/Evolution) NICHT Ende-
    zu-Ende-verschlüsselt — ein einfacher zweistufiger Abruf (getFile ->
    file_path) liefert eine direkt herunterladbare URL, ganz ohne
    Entschlüsselung wie bei evolution_api.get_media_base64().
    """
    response = requests.get(f"{BASE_URL}/getFile", params={"file_id": file_id}, timeout=20)
    response.raise_for_status()
    file_path = response.json()["result"]["file_path"]
    return f"{FILE_BASE_URL}/{file_path}"


def extract_incoming_message(update: dict) -> dict | None:
    """
    Parst ein Telegram-Update (Webhook-Body) in dasselbe vereinfachte Format
    wie evolution_api.extract_incoming_message() — siehe dort für die
    Feldbedeutung. phone ist hier die Chat-ID mit "tg:"-Prefix (siehe
    app/services/messaging.py), damit sie sich nie mit einer echten
    WhatsApp-Telefonnummer überschneiden kann.
    """
    try:
        message = update.get("message") or update.get("edited_message")
        if not message:
            return None

        chat_id = message["chat"]["id"]
        phone = f"tg:{chat_id}"
        message_id = message.get("message_id")
        timestamp = message.get("date")

        if "text" in message:
            return {
                "phone": phone, "type": "text", "content": message["text"],
                "message_id": message_id, "timestamp": timestamp,
            }

        if "voice" in message:
            return {
                "phone": phone,
                "type": "audio",
                "file_id": message["voice"]["file_id"],
                "message_id": message_id, "timestamp": timestamp,
            }

        logger.warning(
            "Unbekannter Telegram-Update-Typ, ignoriert. message-Keys: %s",
            list(message.keys()),
        )
        return None
    except (KeyError, AttributeError):
        logger.exception("Telegram-Update konnte nicht geparst werden: %s", str(update)[:1500])
        return None


def set_webhook(url: str) -> dict:
    response = requests.post(f"{BASE_URL}/setWebhook", json={"url": url}, timeout=20)
    response.raise_for_status()
    return response.json()
