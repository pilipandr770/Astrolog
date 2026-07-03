"""
Страницы, на которые Stripe Checkout редиректит браузер после оплаты
(success_url/cancel_url в stripe_service.create_checkout_session). Реальная
логика после оплаты идёт через /stripe/webhook, а не через эти страницы —
они нужны только чтобы у пользователя не было 404 в браузере, пока он
возвращается в WhatsApp.
"""
from flask import Blueprint

payment_pages_bp = Blueprint("payment_pages", __name__)

_PAGE = """<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><title>{title}</title></head>
<body style="font-family: sans-serif; text-align: center; padding: 3rem;">
<h1>{title}</h1><p>{message}</p>
</body></html>"""


@payment_pages_bp.route("/payment/success")
def payment_success():
    return _PAGE.format(
        title="Zahlung erfolgreich",
        message="Danke! Du kannst jetzt zu WhatsApp zurückkehren — dein Bericht wird dort in Kürze ankommen.",
    )


@payment_pages_bp.route("/payment/cancel")
def payment_cancel():
    return _PAGE.format(
        title="Zahlung abgebrochen",
        message="Die Zahlung wurde abgebrochen. Du kannst es in WhatsApp jederzeit erneut versuchen.",
    )
