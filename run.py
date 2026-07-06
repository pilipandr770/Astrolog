import logging

from flask import Flask
from app.db import init_db
from app.routes.webhook import webhook_bp
from app.routes.stripe_webhook import stripe_webhook_bp
from app.routes.payment_pages import payment_pages_bp
from app.services.payment_poller import start_background_poller

# Ohne das hier landen logger.info()/logger.warning() im ganzen Projekt
# nirgendwo (Python liefert ohne konfigurierten Handler nur WARNING+ über
# einen "last resort"-Handler an stderr aus) — in der Praxis fehlten so
# z.B. alle Erfolgsmeldungen und nicht-fatale Warnungen in `docker logs`.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def create_app():
    app = Flask(__name__)
    init_db()

    app.register_blueprint(webhook_bp)
    app.register_blueprint(stripe_webhook_bp)
    app.register_blueprint(payment_pages_bp)

    # Ersetzt den Stripe-Webhook durch Polling — siehe
    # app/services/payment_poller.py (Grund: kein öffentlicher HTTPS-Endpunkt).
    start_background_poller()

    @app.route("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
