"""
Приём входящих сообщений от Evolution API. Извлекает сообщение из вебхука
и передаёт всю диалоговую логику в app.services.dialog_manager.
"""
from flask import Blueprint, request, jsonify
from app.services import evolution_api, dialog_manager

webhook_bp = Blueprint("webhook", __name__)


@webhook_bp.route("/webhook/evolution", methods=["POST"])
def evolution_webhook():
    payload = request.get_json(silent=True) or {}
    message = evolution_api.extract_incoming_message(payload)

    if message is None:
        return jsonify({"status": "ignored"}), 200

    dialog_manager.handle_message(message["phone"], message)

    return jsonify({"status": "ok"}), 200
