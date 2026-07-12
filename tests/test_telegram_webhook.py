import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

import pytest
from flask import Flask

from app.routes.telegram_webhook import telegram_webhook_bp


@pytest.fixture()
def client():
    app = Flask(__name__)
    app.register_blueprint(telegram_webhook_bp)
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def test_text_message_dispatches_to_dialog_manager(client):
    payload = {
        "update_id": 1,
        "message": {
            "message_id": 42, "date": 1234567890,
            "chat": {"id": 987654321}, "text": "Hallo!",
        },
    }
    with patch("app.routes.telegram_webhook.dialog_manager.handle_message") as mock_handle:
        resp = client.post("/webhook/telegram", json=payload)

    assert resp.status_code == 200
    mock_handle.assert_called_once()
    assert mock_handle.call_args[0][0] == "tg:987654321"
    assert mock_handle.call_args[0][1]["content"] == "Hallo!"


def test_unparseable_update_returns_ignored(client):
    with patch("app.routes.telegram_webhook.dialog_manager.handle_message") as mock_handle:
        resp = client.post("/webhook/telegram", json={"update_id": 1, "sticker": {}})

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ignored"
    mock_handle.assert_not_called()


def test_malformed_body_does_not_crash(client):
    resp = client.post("/webhook/telegram", data="not json", content_type="text/plain")
    assert resp.status_code == 200
