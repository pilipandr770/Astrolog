"""
Dünner Dispatcher, der WhatsApp (evolution_api) und Telegram (telegram_api)
hinter einer gemeinsamen send_text/send_document-Signatur vereint (siehe
Chat-Diskussion "Telegram als Duplikat-Interface"). dialog_manager,
report_generator und payment_poller rufen ausschließlich diese Funktionen
auf, nie evolution_api/telegram_api direkt zum Senden — Telegram-Kontakte
werden an ihrer "tg:"-ID erkannt (siehe telegram_api.extract_incoming_message).
"""
from app.services import evolution_api, telegram_api

TELEGRAM_PREFIX = "tg:"


def is_telegram(phone: str) -> bool:
    return phone.startswith(TELEGRAM_PREFIX)


def _telegram_chat_id(phone: str) -> str:
    return phone[len(TELEGRAM_PREFIX):]


def send_text(phone: str, text: str) -> list[dict]:
    if is_telegram(phone):
        return telegram_api.send_text(_telegram_chat_id(phone), text)
    return evolution_api.send_text(phone, text)


def send_document(phone: str, file_path: str, filename: str, caption: str = "") -> dict:
    if is_telegram(phone):
        return telegram_api.send_document(_telegram_chat_id(phone), file_path, filename, caption)
    return evolution_api.send_document(phone, file_path, filename, caption)
