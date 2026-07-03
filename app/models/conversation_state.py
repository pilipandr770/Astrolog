"""
Простая диалоговая state machine, состояние хранится в SQLite (таблица
conversations из app/db.py). Состояния:

    new -> awaiting_date -> awaiting_time -> awaiting_place
        -> awaiting_payment -> paid -> report_sent

Переходы и парсинг свободного текста реализованы в
app/services/dialog_manager.py и app/services/message_parser.py.

Формат хранения (для будущего пайплайна ephemeris в TODO.md п.4):
    birth_date — ISO "YYYY-MM-DD"
    birth_time — "HH:MM" либо "unbekannt", если пользователь время не знает
"""
from app.db import get_connection


def get_or_create(phone: str) -> dict:
    conn = get_connection()
    row = conn.execute("SELECT * FROM conversations WHERE phone = ?", (phone,)).fetchone()
    if row is None:
        conn.execute("INSERT INTO conversations (phone, state) VALUES (?, 'new')", (phone,))
        conn.commit()
        row = conn.execute("SELECT * FROM conversations WHERE phone = ?", (phone,)).fetchone()
    conn.close()
    return dict(row)


def update(phone: str, **fields):
    conn = get_connection()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [phone]
    conn.execute(
        f"UPDATE conversations SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE phone = ?",
        values,
    )
    conn.commit()
    conn.close()


def find_awaiting_payment() -> list[dict]:
    """Für app/services/payment_poller.py — Stripe-Statusabfrage statt Webhook."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM conversations WHERE state = 'awaiting_payment' AND stripe_session_id IS NOT NULL"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_stats() -> dict:
    """Für die Admin-Oberfläche (app/routes/admin.py) — Zahlungsstatistik."""
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) AS c FROM conversations").fetchone()["c"]
    paid = conn.execute("SELECT COUNT(*) AS c FROM conversations WHERE paid = 1").fetchone()["c"]
    by_state_rows = conn.execute(
        "SELECT state, COUNT(*) AS c FROM conversations GROUP BY state"
    ).fetchall()
    recent_paid = conn.execute(
        "SELECT phone, birth_place, updated_at FROM conversations "
        "WHERE paid = 1 ORDER BY updated_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return {
        "total_conversations": total,
        "paid_count": paid,
        "by_state": {row["state"]: row["c"] for row in by_state_rows},
        "recent_paid": [dict(row) for row in recent_paid],
    }
