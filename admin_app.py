"""
Eigener Flask-Prozess für die Admin-Oberfläche (app/routes/admin.py) — läuft
auf einem separaten Port (Config.ADMIN_PORT), getrennt vom öffentlichen
Bot-Webhook in run.py. Siehe docker-compose.yml: dieser Port wird bewusst
NICHT öffentlich veröffentlicht (nur an 127.0.0.1 gebunden) — Zugriff via
SSH-Tunnel (`ssh -L 5001:localhost:5001 user@vps`).
"""
from flask import Flask

from app.config import Config
from app.db import init_db
from app.routes.admin import admin_bp


def create_admin_app():
    # template_folder explizit setzen: admin_app.py liegt im Projekt-Root,
    # Flasks Standardsuche wäre sonst ./templates statt app/templates.
    app = Flask(__name__, template_folder="app/templates")
    app.secret_key = Config.SECRET_KEY
    init_db()
    app.register_blueprint(admin_bp)
    return app


app = create_admin_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=Config.ADMIN_PORT, debug=False)
