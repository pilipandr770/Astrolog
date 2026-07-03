"""
Admin-Oberfläche: Login, Zahlungsstatistik, zusätzliche Anweisungen für
Claude, Link zum Evolution-API-Manager (QR-Code zum Verbinden/Wechseln der
WhatsApp-Nummer). Läuft als eigener Flask-Prozess auf einem separaten Port
(siehe admin_app.py, docker-compose.yml) — bewusst NICHT öffentlich
veröffentlicht (nur an 127.0.0.1 gebunden), Passwort als zweite
Absicherungsebene.
"""
import secrets
from functools import wraps

from flask import Blueprint, redirect, render_template, request, session, url_for

from app.config import Config
from app.models import conversation_state, settings

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

INSTRUCTIONS_KEY = "extra_claude_instructions"


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)
    return wrapped


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        if Config.ADMIN_PASSWORD and secrets.compare_digest(password, Config.ADMIN_PASSWORD):
            session["is_admin"] = True
            return redirect(url_for("admin.dashboard"))
        error = "Falsches Passwort."
    return render_template("admin_login.html", error=error)


@admin_bp.route("/logout")
def logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin.login"))


@admin_bp.route("/")
@login_required
def dashboard():
    stats = conversation_state.get_stats()
    try:
        revenue = stats["paid_count"] * float(Config.REPORT_PRICE_EUR)
    except ValueError:
        revenue = None
    return render_template(
        "admin_dashboard.html",
        stats=stats,
        revenue=revenue,
        report_price=Config.REPORT_PRICE_EUR,
        evolution_manager_url=Config.EVOLUTION_MANAGER_URL,
    )


@admin_bp.route("/instructions", methods=["GET", "POST"])
@login_required
def instructions():
    saved = False
    if request.method == "POST":
        settings.set_setting(INSTRUCTIONS_KEY, request.form.get("instructions", "").strip())
        saved = True
    current = settings.get_setting(INSTRUCTIONS_KEY, "")
    return render_template("admin_instructions.html", current=current, saved=saved)
