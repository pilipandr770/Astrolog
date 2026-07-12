import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev")
    DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/bot.db")

    EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "")
    EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
    EVOLUTION_INSTANCE_NAME = os.getenv("EVOLUTION_INSTANCE_NAME", "")

    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    WHISPER_MODE = os.getenv("WHISPER_MODE", "api")

    GEOCODING_USER_AGENT = os.getenv("GEOCODING_USER_AGENT", "whatsapp-astrologer-bot")

    # Publiker Server-URL — nur relevant, falls ihr /payment/success und
    # /payment/cancel selbst hostet (siehe routes/payment_pages.py). Im
    # Standardfall (kein Domain/Tunnel, siehe BOT_WHATSAPP_NUMBER unten)
    # wird stattdessen ein wa.me-Link verwendet und diese Variable bleibt
    # ungenutzt.
    APP_BASE_URL = os.getenv("APP_BASE_URL", "")

    # Telefonnummer des Bots im internationalen Format ohne "+"/Leerzeichen
    # (z.B. "4915123456789") — Stripe success_url/cancel_url führen den
    # Nutzer nach der Zahlung per wa.me-Link direkt zurück in den
    # WhatsApp-Chat, ganz ohne eigene öffentlich erreichbare Seite.
    BOT_WHATSAPP_NUMBER = os.getenv("BOT_WHATSAPP_NUMBER", "")

    EPHE_PATH = os.getenv("EPHE_PATH", "./ephe")

    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
    REPORT_PRICE_EUR = os.getenv("REPORT_PRICE_EUR", "9.90")

    # --- Admin-Oberfläche (app/routes/admin.py, admin_app.py) ---
    # Läuft als eigener Prozess auf einem separaten Port, der NICHT
    # öffentlich veröffentlicht werden soll (siehe docker-compose.yml —
    # nur an 127.0.0.1 gebunden, Zugriff via SSH-Tunnel). Passwort trotzdem
    # als zweite Absicherungsebene.
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
    ADMIN_PORT = int(os.getenv("ADMIN_PORT", "5001"))
    # URL des eingebauten Evolution-API-Managers (QR-Code zum Verbinden/
    # Wechseln der WhatsApp-Nummer) — wird in der Admin-Oberfläche verlinkt.
    EVOLUTION_MANAGER_URL = os.getenv("EVOLUTION_MANAGER_URL", "")

    # Intervall für das Payment-Polling (statt Webhook, siehe payment_poller.py)
    PAYMENT_POLL_INTERVAL_SECONDS = int(os.getenv("PAYMENT_POLL_INTERVAL_SECONDS", "90"))
    # Bei gunicorn mit mehreren Workern würde jeder Worker einen eigenen
    # Poller-Thread starten (doppelte/mehrfache Nachrichten!). Auf "false"
    # setzen und den Poller stattdessen separat starten (siehe
    # payment_poller.py, `python -m app.services.payment_poller`), sobald
    # mehr als 1 Worker verwendet wird.
    ENABLE_INPROCESS_PAYMENT_POLLER = os.getenv("ENABLE_INPROCESS_PAYMENT_POLLER", "true").lower() == "true"

    # Nachhol-Sync für verpasste Nachrichten (siehe app/services/catchup.py) —
    # ausgelöst durch das CONNECTION_UPDATE-Webhook-Event, wenn die
    # WhatsApp-Verbindung wieder auf "open" wechselt (nicht periodisch).
    ENABLE_CATCHUP_SYNC = os.getenv("ENABLE_CATCHUP_SYNC", "true").lower() == "true"
    # Schutz gegen zu häufige Läufe, falls die Verbindung kurz hintereinander
    # mehrfach flattert (mehrere CONNECTION_UPDATE-Events in Folge).
    CATCHUP_MIN_INTERVAL_SECONDS = int(os.getenv("CATCHUP_MIN_INTERVAL_SECONDS", "60"))
