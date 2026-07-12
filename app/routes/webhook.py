"""
Приём входящих сообщений от Evolution API. Извлекает сообщение из вебхука
и передаёт всю диалоговую логику в app.services.dialog_manager.

Дополнительно слушает CONNECTION_UPDATE (см. docs/TODO.md / Chat-Diskussion
"пропущенные сообщения при разрыве связи") — при переходе в state="open"
запускает app.services.catchup.run_after_reconnect(), чтобы бот дообработал
входящие сообщения, которые пришли, пока соединение с WhatsApp было разорвано
(Evolution в этом окне не шлёт вебхук, но синхронизирует историю чата задним
числом — см. catchup.py).
"""
import logging

from flask import Blueprint, request, jsonify
from app.services import evolution_api, dialog_manager, catchup

logger = logging.getLogger(__name__)

webhook_bp = Blueprint("webhook", __name__)

# Evolution schickt den Event-Namen mal als "connection.update" (Punkt-Form,
# im Payload-Body), mal referenzieren wir ihn als "CONNECTION_UPDATE"
# (Unterstrich-Form, in der Webhook-Subscription selbst) — hier beide Formen
# tolerieren, statt uns auf eine zu verlassen.
_CONNECTION_UPDATE_EVENTS = {"connection.update", "CONNECTION_UPDATE"}


@webhook_bp.route("/webhook/evolution", methods=["POST"])
def evolution_webhook():
    payload = request.get_json(silent=True) or {}
    event = payload.get("event")

    if event in _CONNECTION_UPDATE_EVENTS:
        state = (payload.get("data") or {}).get("state")
        logger.info("CONNECTION_UPDATE empfangen: state=%s | Payload: %s", state, str(payload)[:1000])
        if state == "open":
            catchup.run_after_reconnect()
        return jsonify({"status": "ok"}), 200

    message = evolution_api.extract_incoming_message(payload)

    if message is None:
        return jsonify({"status": "ignored"}), 200

    dialog_manager.handle_message(message["phone"], message)

    return jsonify({"status": "ok"}), 200
