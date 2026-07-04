"""
Диалоговая state machine: new/sales_chat -> awaiting_date -> awaiting_time ->
awaiting_place -> awaiting_style -> awaiting_payment -> paid -> report_sent.

new/sales_chat: freies Verkaufsgespräch (siehe _handle_sales_chat) — Claude
beantwortet Fragen, erklärt ehrlich Berechnung vs. Interpretation, und
entscheidet selbst (über das start_intake-Tool, siehe claude_service.py),
wann der Nutzer bereit für die strukturierte Datenerfassung ist. Erst danach
beginnt der feste State machine-Teil (Datum/Zeit/Ort/Stil) unverändert.

Переход awaiting_payment -> paid отслеживается через опрос Stripe (см.
app/services/payment_poller.py), а не через вебхук — сервер разворачивается
на VPS без публичного HTTPS-адреса. Переход paid -> report_sent (генерация
отчёта) — см. docs/TODO.md, пункт 4, ещё предстоит подключить. Этот модуль
отвечает только за сбор данных рождения, стиля/языка и создание ссылки на
оплату.

Язык и стиль тизера/отчёта (см. claude_service.py):
- Диалог сбора данных (даты/время/место, ошибки) остаётся на немецком —
  сознательно не переводим, см. обсуждение в чате.
- Сам гороскоп (тизер, полный отчёт, PDF) адаптируется под язык, на
  котором пишет пользователь — определяет это сам Claude по переданному
  сигналу (language_hint от Whisper для голосовых, иначе language_sample —
  текст первого сообщения пользователя).
- Стиль (шутливый/деловой/тёплый/романтичный) пользователь выбирает сам
  после указания места рождения (_handle_style()).
"""
import json
import logging
from datetime import date

from app.config import Config
from app.models import conversation_state
from app.services import (
    claude_service,
    evolution_api,
    geocoding,
    message_parser,
    natal_chart,
    report_generator,
    stripe_service,
    whisper_service,
)

logger = logging.getLogger(__name__)

RESET_WORDS = {"neu", "neustart", "reset", "von vorne", "заново", "начать заново"}

# Feste Reihenfolge für das nummerierte Stil-Menü (siehe _style_menu_text()) —
# entspricht der Einfügereihenfolge in claude_service.STYLE_PRESETS, aber
# explizit gehalten, damit die Nummerierung nicht von Dict-Details abhängt.
_STYLE_ORDER = ["warm", "humorous", "business", "romantic"]

# Begrenzt das gespeicherte Verkaufsgespräch (siehe _handle_sales_chat) auf die
# letzten N Turns (1 Turn = 1 User- + 1 Assistant-Nachricht) — verhindert
# unbegrenztes Token-Wachstum bei sehr gesprächigen Interessenten.
MAX_SALES_HISTORY_TURNS = 8


def handle_message(phone: str, message: dict) -> None:
    text = _extract_text(phone, message)
    if text is None:
        return  # ошибка транскрипции уже сообщена пользователю в _extract_text

    state = conversation_state.get_or_create(phone)

    if text.strip().lower() in RESET_WORDS and state["state"] != "new":
        conversation_state.update(
            phone,
            state="new",
            birth_date=None,
            birth_time=None,
            birth_place=None,
            birth_lat=None,
            birth_lon=None,
            birth_tz=None,
            style=None,
            paid=0,
            stripe_session_id=None,
            sales_chat_history=None,
        )
        state = conversation_state.get_or_create(phone)

    _capture_language_signal(phone, state, text)

    current = state["state"]

    if current in ("new", "sales_chat"):
        _handle_sales_chat(phone, text, state)
    elif current == "awaiting_date":
        _handle_date(phone, text)
    elif current == "awaiting_time":
        _handle_time(phone, text)
    elif current == "awaiting_place":
        _handle_place(phone, text)
    elif current == "awaiting_style":
        _handle_style(phone, text, state)
    elif current == "awaiting_payment":
        _remind_payment(phone, state)
    elif current == "paid":
        # Zustand "paid" bedeutet: bezahlt, aber der Bericht wurde noch nicht
        # (erfolgreich) zugestellt — z.B. weil die erste Generierung im
        # Poller fehlgeschlagen ist. Jede Nachricht triggert einen neuen
        # Versuch (report_generator schützt selbst vor Doppel-Läufen).
        evolution_api.send_text(
            phone,
            "Danke für deine Zahlung! Dein Bericht wird gerade erstellt — "
            "das dauert nur ein paar Minuten.",
        )
        report_generator.generate_and_send_report(phone)
    elif current == "report_sent":
        evolution_api.send_text(
            phone,
            "Dein Bericht wurde bereits gesendet. Wenn du eine neue Auswertung "
            "möchtest (z. B. für eine andere Person), schreib 'neu'.",
        )
    else:
        logger.warning("Unbekannter Zustand '%s' für %s", current, phone)
        _handle_sales_chat(phone, text, state)


def _extract_text(phone: str, message: dict) -> str | None:
    if message["type"] == "text":
        return message["content"]

    if message["type"] == "audio":
        try:
            # Die Webhook-URL ist E2E-verschlüsselt und direkt unbrauchbar —
            # das entschlüsselte Audio liefert nur Evolution selbst
            # (siehe evolution_api.get_media_base64).
            media = evolution_api.get_media_base64(message["message_key"])
            result = whisper_service.transcribe_from_base64(
                media["base64"], media.get("mimetype")
            )
        except Exception:
            logger.exception("Whisper-Transkription fehlgeschlagen für %s", phone)
            evolution_api.send_text(
                phone,
                "Ich konnte deine Sprachnachricht leider nicht verstehen. "
                "Kannst du es bitte als Text senden?",
            )
            return None

        if result.get("language"):
            # Von Whisper explizit erkannt — zuverlässiger als eine
            # Textprobe, deshalb wird sie hier bevorzugt gespeichert.
            conversation_state.update(phone, language_hint=result["language"])
        return result["text"]

    return None


def _capture_language_signal(phone: str, state: dict, text: str) -> None:
    """
    Speichert eine Textprobe der ERSTEN Nutzernachricht als Sprachsignal
    für claude_service._language_directive() — nur falls noch kein
    Signal vorliegt (weder Whisper-language_hint noch eine frühere Probe)
    und der Text tatsächlich Inhalt hat.
    """
    if state.get("language_hint") or state.get("language_sample"):
        return
    if text and text.strip():
        conversation_state.update(phone, language_sample=text.strip()[:200])


def _handle_sales_chat(phone: str, text: str, state: dict) -> None:
    """
    Freies Verkaufsgespräch vor der Datenerfassung — ersetzt die frühere feste
    Begrüßungsnachricht. Claude beantwortet Fragen ehrlich, erklärt den Service
    und ruft selbst (via claude_service.START_INTAKE_TOOL) den Wechsel in die
    strukturierte Erfassung aus, sobald der Nutzer bereit wirkt.
    """
    history = json.loads(state.get("sales_chat_history") or "[]")

    try:
        reply_text, ready = claude_service.generate_sales_reply(state, history, text)
    except Exception:
        logger.exception("Sales-Chat-Antwort fehlgeschlagen für %s", phone)
        evolution_api.send_text(
            phone,
            "Entschuldige, gerade gab es ein technisches Problem. Kannst du "
            "das bitte noch einmal schreiben?",
        )
        return

    if not reply_text:
        # Sollte durch den Prompt praktisch nie vorkommen, aber eine leere
        # WhatsApp-Nachricht wäre verwirrend — lieber eine Rückfrage senden.
        reply_text = "Magst du mir noch etwas mehr erzählen, was dich interessiert?"

    history = history + [
        {"role": "user", "content": text},
        {"role": "assistant", "content": reply_text},
    ]
    history = history[-(MAX_SALES_HISTORY_TURNS * 2):]

    if ready:
        conversation_state.update(
            phone, state="awaiting_date", sales_chat_history=None
        )
        evolution_api.send_text(phone, reply_text)
        evolution_api.send_text(
            phone,
            "Bitte sende mir dein Geburtsdatum, z. B. 15.05.1990. 🎙 Du kannst "
            "mir übrigens auch eine Sprachnachricht schicken.",
        )
    else:
        conversation_state.update(
            phone, state="sales_chat", sales_chat_history=json.dumps(history)
        )
        evolution_api.send_text(phone, reply_text)


def _handle_date(phone: str, text: str) -> None:
    parsed = message_parser.parse_birth_date(text)
    if parsed is None:
        evolution_api.send_text(
            phone,
            "Entschuldigung, das Datum konnte ich nicht erkennen. "
            "Bitte sende es z. B. so: 15.05.1990 oder '15. Mai 1990'.",
        )
        return

    conversation_state.update(phone, birth_date=parsed.isoformat(), state="awaiting_time")
    evolution_api.send_text(
        phone,
        f"Danke! Geburtsdatum notiert: {parsed.strftime('%d.%m.%Y')}.\n\n"
        "Jetzt brauche ich deine Geburtszeit, z. B. 14:30. Falls du sie nicht "
        "genau weißt, schreib einfach 'weiß nicht'.",
    )


def _handle_time(phone: str, text: str) -> None:
    parsed = message_parser.parse_birth_time(text)
    if parsed is None:
        evolution_api.send_text(
            phone,
            "Ich konnte die Uhrzeit nicht erkennen. Bitte sende sie z. B. so: "
            "14:30, oder schreibe 'weiß nicht', falls du sie nicht kennst.",
        )
        return

    if parsed == "unknown":
        birth_time_value = "unbekannt"
    else:
        hour, minute = parsed
        birth_time_value = f"{hour:02d}:{minute:02d}"

    conversation_state.update(phone, birth_time=birth_time_value, state="awaiting_place")
    evolution_api.send_text(
        phone,
        "Perfekt. Zum Schluss: In welcher Stadt (und welchem Land) bist du "
        "geboren? (z. B. 'Frankfurt am Main, Deutschland')",
    )


def _handle_place(phone: str, text: str) -> None:
    try:
        geo = geocoding.geocode_place(text)
    except ValueError:
        evolution_api.send_text(
            phone,
            f"Ich konnte den Ort '{text.strip()}' leider nicht finden. "
            "Bitte versuche es genauer, z. B. 'Berlin, Deutschland'.",
        )
        return
    except Exception:
        logger.exception("Geocoding fehlgeschlagen für %s", phone)
        evolution_api.send_text(
            phone,
            "Bei der Suche nach deinem Geburtsort ist ein Fehler aufgetreten. "
            "Bitte versuche es gleich noch einmal.",
        )
        return

    conversation_state.update(
        phone,
        birth_place=geo["display_name"],
        birth_lat=geo["lat"],
        birth_lon=geo["lon"],
        birth_tz=geo["tz_name"],
        state="awaiting_style",
    )
    evolution_api.send_text(phone, _style_menu_text())


def _style_menu_text() -> str:
    lines = ["Für wen ist diese Auswertung gedacht? Wähle einen Stil, indem du die Zahl schickst:"]
    for number, key in enumerate(_STYLE_ORDER, start=1):
        label = claude_service.STYLE_PRESETS[key]["label"]
        default_note = " (Standard)" if key == claude_service.DEFAULT_STYLE_KEY else ""
        lines.append(f"{number}️⃣ {label}{default_note}")
    return "\n".join(lines)


def _handle_style(phone: str, text: str, state: dict) -> None:
    digit = next((ch for ch in text.strip() if ch in "1234"), None)
    if digit is None:
        evolution_api.send_text(
            phone,
            "Bitte antworte nur mit einer Zahl von 1 bis 4.\n\n" + _style_menu_text(),
        )
        return

    style_key = _STYLE_ORDER[int(digit) - 1]
    conversation_state.update(phone, style=style_key, state="awaiting_payment")
    state = conversation_state.get_or_create(phone)

    _send_teaser(phone, state)
    _send_payment_link(phone, state, with_summary=True)


def _pick_teaser_findings(findings: list) -> list:
    """
    Wählt 1-2 Befunde für den kostenlosen Teaser aus (siehe Chat-Entscheidung:
    "ein bis zwei lebendige Treffer aus der Karte", nicht die volle Liste).
    Moon steht in Lal Kitab für Geist/Gemüt und wird bevorzugt einbezogen;
    Sun/Jupiter als zweiter, meist positiv gefärbter Treffer.
    """
    by_planet = {f.planet: f for f in findings}
    picks = []
    moon = by_planet.get("Moon")
    if moon:
        picks.append(moon)
    for planet in ("Sun", "Jupiter"):
        candidate = by_planet.get(planet)
        if candidate and candidate not in picks:
            picks.append(candidate)
            break
    return picks[:2]


def _send_teaser(phone: str, state: dict) -> None:
    try:
        chart = natal_chart.compute(state)
    except Exception:
        logger.exception("Geburtskarten-Berechnung für Teaser fehlgeschlagen für %s", phone)
        return  # kein Teaser, aber der Zahlungslink wird trotzdem verschickt

    teaser_findings = _pick_teaser_findings(chart["findings"])
    if not teaser_findings:
        return

    try:
        teaser_text = claude_service.generate_teaser(state, chart["houses"], teaser_findings)
    except Exception:
        logger.exception("Teaser-Text-Generierung fehlgeschlagen für %s", phone)
        return

    evolution_api.send_text(phone, teaser_text)


def _payment_redirect_urls() -> tuple[str, str]:
    """
    Stripe verlangt gültige success_url/cancel_url, aber ohne eigene
    öffentliche Domain (siehe payment_poller.py) müssen das keine
    selbst gehosteten Seiten sein — ein wa.me-Link führt den Nutzer direkt
    zurück in den WhatsApp-Chat. Falls APP_BASE_URL gesetzt ist (z.B. weil
    doch eine Domain/ein Tunnel eingerichtet wurde), werden stattdessen die
    Seiten aus routes/payment_pages.py verwendet.
    """
    if Config.APP_BASE_URL:
        return (
            f"{Config.APP_BASE_URL}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
            f"{Config.APP_BASE_URL}/payment/cancel",
        )
    return (
        f"https://wa.me/{Config.BOT_WHATSAPP_NUMBER}?text=Zahlung%20abgeschlossen",
        f"https://wa.me/{Config.BOT_WHATSAPP_NUMBER}?text=Zahlung%20abgebrochen",
    )


def _send_payment_link(phone: str, state: dict, with_summary: bool) -> None:
    success_url, cancel_url = _payment_redirect_urls()

    try:
        session = stripe_service.create_checkout_session(phone, success_url, cancel_url)
    except Exception:
        logger.exception("Stripe-Checkout-Session fehlgeschlagen für %s", phone)
        evolution_api.send_text(
            phone,
            "Bei der Erstellung des Zahlungslinks ist ein Fehler aufgetreten. "
            "Bitte versuche es gleich noch einmal.",
        )
        return

    conversation_state.update(phone, stripe_session_id=session["id"])
    _send_payment_message(phone, state, session["url"], with_summary)


def _remind_payment(phone: str, state: dict) -> None:
    """
    Bei erneuter Nachricht im Status awaiting_payment: die bestehende
    Checkout-Session wiederverwenden (kein neuer Link/keine neue Session),
    solange sie noch offen ist. Das hält payment_poller.py in Sync — sonst
    würde jede Erinnerung eine neue Session anlegen, aber nur die zuletzt
    gespeicherte stripe_session_id würde noch abgefragt.
    """
    session_id = state.get("stripe_session_id")
    checkout_url = None
    if session_id:
        try:
            session = stripe_service.get_session(session_id)
            if session.status == "open":
                checkout_url = session.url
        except Exception:
            logger.exception("Stripe-Session-Abfrage fehlgeschlagen für %s", phone)

    if checkout_url is None:
        _send_payment_link(phone, state, with_summary=False)
        return

    _send_payment_message(phone, state, checkout_url, with_summary=False)


def _send_payment_message(phone: str, state: dict, checkout_url: str, with_summary: bool) -> None:
    summary = ""
    if with_summary:
        birth_date_display = date.fromisoformat(state["birth_date"]).strftime("%d.%m.%Y")
        summary = (
            "Alles bereit! Deine Angaben:\n"
            f"📅 {birth_date_display}\n"
            f"🕐 {state['birth_time']}\n"
            f"📍 {state['birth_place']}\n\n"
        )

    evolution_api.send_text(
        phone,
        f"{summary}Um deine persönliche Lal-Kitab-Auswertung ({Config.REPORT_PRICE_EUR} €) "
        f"zu erhalten, schließe bitte die Zahlung ab:\n{checkout_url}\n\n"
        "Sobald die Zahlung bestätigt ist, sende ich dir automatisch deinen Bericht.",
    )
