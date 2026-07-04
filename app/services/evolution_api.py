"""
Клиент для Evolution API — отправка текстовых сообщений и документов
в WhatsApp. Сигнатуры соответствуют типовому Evolution API v2 REST,
НО ПРОВЕРЬ версию своего контейнера на Hostinger — эндпоинты и формат
payload могли отличаться между версиями Evolution API.
"""
import base64
import requests
from app.config import Config

BASE_URL = Config.EVOLUTION_API_URL.rstrip("/")
INSTANCE = Config.EVOLUTION_INSTANCE_NAME

HEADERS = {
    "apikey": Config.EVOLUTION_API_KEY,
    "Content-Type": "application/json",
}


def send_text(phone: str, text: str) -> dict:
    url = f"{BASE_URL}/message/sendText/{INSTANCE}"
    payload = {"number": phone, "text": text}
    response = requests.post(url, json=payload, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return response.json()


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
    TODO: сверить с реальной структурой вебхука твоего инстанса —
    структура ниже основана на типовом messages.upsert событии Evolution
    API v2, но могут быть отличия по версии.
    """
    try:
        data = webhook_payload.get("data", {})
        message = data.get("message", {})
        phone = data.get("key", {}).get("remoteJid", "").split("@")[0]

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
                "message_key": data.get("key", {}),
            }

        return None
    except (KeyError, AttributeError):
        return None
