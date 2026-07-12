import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

import pytest
from flask import Flask

from app.routes.webhook import webhook_bp


@pytest.fixture()
def client():
    # Bewusst eine minimale App statt run.py:create_app() — die echte
    # create_app() startet beim Import den Stripe-Payment-Poller und
    # initialisiert die Produktions-DB, was hier nur unnötige Seiteneffekte
    # wären. Für das Webhook-Routing reicht webhook_bp allein.
    app = Flask(__name__)
    app.register_blueprint(webhook_bp)
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def test_connection_update_open_triggers_catchup(client):
    with patch("app.routes.webhook.catchup.run_after_reconnect") as mock_run, \
         patch("app.routes.webhook.dialog_manager.handle_message") as mock_handle:
        resp = client.post("/webhook/evolution", json={
            "event": "CONNECTION_UPDATE",
            "data": {"state": "open"},
        })

    assert resp.status_code == 200
    mock_run.assert_called_once()
    mock_handle.assert_not_called()


def test_connection_update_dot_form_also_recognized(client):
    # Evolution verwendet je nach Kontext "CONNECTION_UPDATE" oder
    # "connection.update" -- beide Schreibweisen muessen erkannt werden.
    with patch("app.routes.webhook.catchup.run_after_reconnect") as mock_run:
        resp = client.post("/webhook/evolution", json={
            "event": "connection.update",
            "data": {"state": "open"},
        })

    assert resp.status_code == 200
    mock_run.assert_called_once()


def test_connection_update_non_open_state_does_not_trigger_catchup(client):
    with patch("app.routes.webhook.catchup.run_after_reconnect") as mock_run:
        resp = client.post("/webhook/evolution", json={
            "event": "CONNECTION_UPDATE",
            "data": {"state": "connecting"},
        })

    assert resp.status_code == 200
    mock_run.assert_not_called()


def test_connection_update_missing_data_does_not_crash(client):
    with patch("app.routes.webhook.catchup.run_after_reconnect") as mock_run:
        resp = client.post("/webhook/evolution", json={"event": "CONNECTION_UPDATE"})

    assert resp.status_code == 200
    mock_run.assert_not_called()


def test_normal_message_still_falls_through_to_dialog_manager(client):
    payload = {
        "event": "messages.upsert",
        "data": {
            "key": {"remoteJid": "491234567@s.whatsapp.net", "fromMe": False, "id": "MSG1"},
            "message": {"conversation": "Hallo!"},
            "messageTimestamp": 123,
        },
    }
    with patch("app.routes.webhook.dialog_manager.handle_message") as mock_handle, \
         patch("app.routes.webhook.catchup.run_after_reconnect") as mock_run:
        resp = client.post("/webhook/evolution", json=payload)

    assert resp.status_code == 200
    mock_handle.assert_called_once()
    assert mock_handle.call_args[0][0] == "491234567"
    mock_run.assert_not_called()


def test_unparseable_payload_returns_ignored(client):
    with patch("app.routes.webhook.dialog_manager.handle_message") as mock_handle:
        resp = client.post("/webhook/evolution", json={"event": "someOtherEvent", "data": {}})

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ignored"
    mock_handle.assert_not_called()


def test_malformed_body_does_not_crash(client):
    resp = client.post("/webhook/evolution", data="not json", content_type="text/plain")
    assert resp.status_code == 200
