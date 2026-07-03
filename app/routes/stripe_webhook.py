"""
Приём событий от Stripe. СТАТУС: верификация подписи работает, но
обработчик checkout.session.completed НЕ триггерит генерацию отчёта —
это TODO (нужно связать с pipeline: ephemeris -> lal_kitab -> claude ->
pdf -> evolution_api.send_document).
"""
from flask import Blueprint, request, jsonify
from app.services import stripe_service
from app.models import conversation_state

stripe_webhook_bp = Blueprint("stripe_webhook", __name__)


@stripe_webhook_bp.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")

    try:
        event = stripe_service.verify_webhook(payload, sig_header)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        phone = session.get("client_reference_id")
        if phone:
            conversation_state.update(phone, paid=1, state="paid", stripe_session_id=session["id"])
            # TODO: здесь запустить генерацию отчёта и отправку PDF,
            # см. docs/TODO.md пункт 3.

    return jsonify({"status": "ok"}), 200
