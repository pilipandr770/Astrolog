import sqlite3
import os
from app.config import Config

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    phone TEXT PRIMARY KEY,
    state TEXT NOT NULL DEFAULT 'new',
    birth_date TEXT,
    birth_time TEXT,
    birth_place TEXT,
    birth_lat REAL,
    birth_lon REAL,
    birth_tz TEXT,
    paid INTEGER DEFAULT 0,
    stripe_session_id TEXT,
    -- Sprachsignal für Teaser/Bericht (claude_service.py) — language_hint
    -- kommt von Whisper (Sprachnachricht, explizite Erkennung, hat Vorrang),
    -- language_sample ist eine Textprobe der ersten Nutzernachricht als
    -- Fallback für Claude zur eigenen Spracherkennung.
    language_hint TEXT,
    language_sample TEXT,
    -- Gewünschter Ton der Auswertung, siehe claude_service.STYLE_PRESETS
    style TEXT,
    -- JSON-Liste der bisherigen Verkaufsgespräch-Turns (siehe
    -- dialog_manager._handle_sales_chat) — nötig, damit Claude über
    -- mehrere Nachrichten hinweg Kontext behält, bevor die strukturierte
    -- Datenerfassung beginnt. Wird beim Übergang zu awaiting_date/bei
    -- Reset wieder geleert.
    sales_chat_history TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Admin-editierbare Einstellungen (z.B. zusätzliche Anweisungen für Claude),
-- siehe app/models/settings.py und app/routes/admin.py
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def get_connection():
    os.makedirs(os.path.dirname(Config.DATABASE_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn, table: str, column: str, coltype: str) -> None:
    """
    Für bereits existierende SQLite-Dateien: CREATE TABLE IF NOT EXISTS
    fügt bei einer schon vorhandenen Tabelle KEINE neuen Spalten hinzu.
    Diese Migration holt das idempotent nach (z.B. beim Hinzufügen von
    language_hint/language_sample/style zu einer bereits laufenden
    Installation).
    """
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    _ensure_column(conn, "conversations", "language_hint", "TEXT")
    _ensure_column(conn, "conversations", "language_sample", "TEXT")
    _ensure_column(conn, "conversations", "style", "TEXT")
    _ensure_column(conn, "conversations", "sales_chat_history", "TEXT")
    conn.commit()
    conn.close()
