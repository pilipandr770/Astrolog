"""
Клиент для Evolution API — отправка текстовых сообщений и документов
в WhatsApp. Сигнатуры соответствуют типовому Evolution API v2 REST,
НО ПРОВЕРЬ версию своего контейнера на Hostinger — эндпоинты и формат
payload могли отличаться между версиями Evolution API.
"""
import base64
import logging

import requests
from app.config import Config

logger = logging.getLogger(__name__)

BASE_URL = Config.EVOLUTION_API_URL.rstrip("/")
INSTANCE = Config.EVOLUTION_INSTANCE_NAME

HEADERS = {
    "apikey": Config.EVOLUTION_API_KEY,
    "Content-Type": "application/json",
}

# WhatsApp-Textnachrichten sind praktisch auf ~4096 Zeichen begrenzt (WhatsApp
# Business API / Baileys) — mit Sicherheitsabstand, damit lange Claude-Antworten
# (Sales-Chat, Teaser, Coach) nicht mitten im Satz abgeschnitten werden.
MAX_TEXT_LENGTH = 3500


def _find_split_point(text: str, max_length: int) -> int:
    """
    Sucht die beste Trennstelle innerhalb der ersten max_length Zeichen —
    bevorzugt Absatz-, dann Zeilenumbruch, dann Satzende, zuletzt Wortgrenze.
    Wird nur akzeptiert, wenn sie nicht zu früh liegt (sonst lieber hart am
    Limit schneiden, als eine winzige erste Nachricht zu erzeugen).
    """
    window = text[:max_length]
    for separator in ("\n\n", "\n", ". ", " "):
        idx = window.rfind(separator)
        if idx >= max_length * 0.5:
            return idx + len(separator)
    return max_length


def _split_text(text: str, max_length: int = MAX_TEXT_LENGTH) -> list[str]:
    """Teilt langen Text in mehrere WhatsApp-taugliche Nachrichten-Chunks."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    remaining = text
    while len(remaining) > max_length:
        split_at = _find_split_point(remaining, max_length)
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def send_text(phone: str, text: str) -> list[dict]:
    """
    Sendet Text an WhatsApp. Lange Texte werden automatisch in mehrere
    Nachrichten aufgeteilt (siehe _split_text) statt vom Empfänger
    abgeschnitten zu werden — Chunks gehen sequenziell raus, damit die
    Reihenfolge beim Empfänger erhalten bleibt.
    """
    url = f"{BASE_URL}/message/sendText/{INSTANCE}"
    responses = []
    for chunk in _split_text(text):
        payload = {"number": phone, "text": chunk}
        response = requests.post(url, json=payload, headers=HEADERS, timeout=20)
        response.raise_for_status()
        responses.append(response.json())
    return responses


def send_document(phone: str, file_path: str, filename: str, caption: str = "") -> dict:
    url = f"{BASE_URL}/message/sendMedia/{INSTANCE}"
    with open(file_path, "rb") as f:
        file_b64 = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "number": phone,
        "mediatype": "document",
        "mimetype": "application/pdf",
        "media": file_b64,
        "fileName": filename,
        "caption": caption,
    }
    response = requests.post(url, json=payload, headers=HEADERS, timeout=60)
    response.raise_for_status()
    return response.json()


def get_media_base64(message_key: dict) -> dict:
    """
    Holt das ENTSCHLÜSSELTE Medium einer Nachricht als Base64 über
    Evolution API (/chat/getBase64FromMediaMessage). Wichtig: die URL im
    Webhook zeigt auf mmg.whatsapp.net/...enc — das ist die Ende-zu-Ende-
    verschlüsselte Datei, ein direkter Download liefert unbrauchbare Bytes
    (OpenAI antwortet dann mit 'Invalid file format'). Nur Evolution selbst
    besitzt die Schlüssel zum Entschlüsseln.

    Rückgabe (Evolution v2): {"mediaType": ..., "mimetype": ..., "base64": ...}
    """
    url = f"{BASE_URL}/chat/getBase64FromMediaMessage/{INSTANCE}"
    payload = {"message": {"key": message_key}, "convertToMp4": False}
    response = requests.post(url, json=payload, headers=HEADERS, timeout=60)
    response.raise_for_status()
    return response.json()


def extract_incoming_message(webhook_payload: dict) -> dict | None:
    """
    Парсит вебхук от Evolution API в упрощённый формат.

    Unbekannte/nicht behandelte Payloads werden NICHT stillschweigend
    verworfen, sondern mit WARNING geloggt (siehe run.py — ohne
    logging.basicConfig dort gingen solche Meldungen bisher komplett
    verloren) — nötig, um z.B. abweichende audioMessage-Formate oder
    andere Webhook-Event-Typen (nicht nur messages.upsert) überhaupt
    diagnostizieren zu können, statt dass der Bot einfach "nicht antwortet".
    """
    try:
        data = webhook_payload.get("data", {})
        key = data.get("key", {})
        message = data.get("message", {})
        phone = key.get("remoteJid", "").split("@")[0]

        if key.get("fromMe"):
            # Echo der eigenen ausgehenden Nachrichten (Evolution schickt
            # messages.upsert auch dafür) — kein Nutzer-Input, ignorieren.
            return None

        if "conversation" in message:
            return {"phone": phone, "type": "text", "content": message["conversation"]}

        if "audioMessage" in message:
            return {
                "phone": phone,
                "type": "audio",
                # media_url ist die E2E-verschlüsselte WhatsApp-URL — nur als
                # Debug-Info behalten. Zum Transkribieren message_key an
                # get_media_base64() geben (siehe dialog_manager._extract_text).
                "media_url": message["audioMessage"].get("url"),
                "message_key": key,
            }

        logger.warning(
            "Unbekannter Webhook-Payload-Typ, ignoriert. message-Keys: %s | voller Payload (gekürzt): %s",
            list(message.keys()), str(webhook_payload)[:1500],
        )
        return None
    except (KeyError, AttributeError):
        logger.exception("Webhook-Payload konnte nicht geparst werden: %s", str(webhook_payload)[:1500])
        return None
