import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.config import Config


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "DATABASE_PATH", str(tmp_path / "test_admin.db"))
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "test123")

    # admin_app wird nur beim allerersten Import wirklich ausgeführt (Modul-
    # Caching) — init_db() hier erneut aufrufen, damit jeder Test sein
    # eigenes frisches tmp_path-DB-Schema bekommt (init_db ist idempotent).
    from app.db import init_db
    init_db()

    import admin_app
    admin_app.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    with admin_app.app.test_client() as c:
        yield c


def test_dashboard_redirects_when_not_logged_in(client):
    resp = client.get("/admin/", follow_redirects=True)
    assert resp.status_code == 200
    assert "Passwort" in resp.get_data(as_text=True)


def test_login_wrong_password_shows_error(client):
    resp = client.post("/admin/login", data={"password": "wrong"})
    assert "Falsches Passwort" in resp.get_data(as_text=True)


def test_login_correct_password_reaches_dashboard(client):
    resp = client.post("/admin/login", data={"password": "test123"}, follow_redirects=True)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "bersicht" in body  # "Übersicht" (Encoding-unabhängiger Teilstring)


def test_logout_requires_login_again(client):
    client.post("/admin/login", data={"password": "test123"})
    client.get("/admin/logout")
    resp = client.get("/admin/", follow_redirects=True)
    assert "Passwort" in resp.get_data(as_text=True)


def test_instructions_roundtrip(client):
    client.post("/admin/login", data={"password": "test123"})
    resp = client.post(
        "/admin/instructions", data={"instructions": "Sei besonders freundlich."}, follow_redirects=True
    )
    assert "Sei besonders freundlich." in resp.get_data(as_text=True)

    # Persisted across a fresh GET too
    resp = client.get("/admin/instructions")
    assert "Sei besonders freundlich." in resp.get_data(as_text=True)
