"""
Stripe Checkout — оплата перед генерацией отчёта. Флоу (без вебхука, см.
app/services/payment_poller.py — бот на VPS без домена/туннеля, поэтому
Stripe не может достучаться пушем; вместо этого бот сам опрашивает статус):
1. После сбора данных рождения бот шлёт пользователю ссылку на Checkout,
   создавая сессию через create_checkout_session() и сохраняя её id.
2. Пользователь платит.
3. payment_poller.py периодически вызывает get_payment_status(session_id)
   для всех разговоров в состоянии awaiting_payment.
4. Как только payment_status == "paid" — запускается генерация отчёта.

Вебхук (routes/stripe_webhook.py, verify_webhook ниже) оставлен как
альтернативный путь на будущее, если сервер получит публичный HTTPS-адрес
(домен, sslip.io, Cloudflare Tunnel) — тогда подтверждение будет мгновенным
вместо задержки на интервал опроса.

client_reference_id используется, чтобы связать сессию оплаты с
номером телефона пользователя в WhatsApp.
"""
import stripe
from app.config import Config

stripe.api_key = Config.STRIPE_SECRET_KEY


def create_checkout_session(phone: str, success_url: str, cancel_url: str) -> dict:
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price": Config.STRIPE_PRICE_ID, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=phone,
    )
    return {"id": session.id, "url": session.url}


def get_session(session_id: str):
    return stripe.checkout.Session.retrieve(session_id)


def get_payment_status(session_id: str) -> str:
    """'paid' | 'unpaid' | 'no_payment_required' — siehe Stripe Checkout Session API."""
    return get_session(session_id).payment_status


def verify_webhook(payload: bytes, sig_header: str):
    return stripe.Webhook.construct_event(payload, sig_header, Config.STRIPE_WEBHOOK_SECRET)
