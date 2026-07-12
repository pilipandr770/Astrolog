"""
Приём входящих сообщений от Telegram Bot API — второй, дублирующий канал
вдобавок к WhatsApp (см. app/routes/webhook.py). Использует ту же
диалоговую логику через app.services.dialog_manager; идентификатор
контакта — "tg:<chat_id>" (см. app/services/messaging.py), полностью
независим от WhatsApp-номеров.
"""
import logging

from flask import Blueprint, request, jsonify
from app.services import telegram_api, dialog_manager

logger = logging.getLogger(__name__)

telegram_webhook_bp = Blueprint("telegram_webhook", __name__)


@telegram_webhook_bp.route("/webhook/telegram", methods=["POST"])
def telegram_webhook():
    payload = request.get_json(silent=True) or {}

    message = telegram_api.extract_incoming_message(payload)
    if message is None:
        return jsonify({"status": "ignored"}), 200

    dialog_manager.handle_message(message["phone"], message)

    return jsonify({"status": "ok"}), 200
