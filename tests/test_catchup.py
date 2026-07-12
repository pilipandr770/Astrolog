import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from app.services import catchup


def test_is_group_chat():
    assert catchup._is_group_chat("12345-6789@g.us") is True
    assert catchup._is_group_chat("491234567@s.whatsapp.net") is False


def test_chat_has_pending_message_true_when_last_message_incoming():
    chat = {"lastMessage": {"key": {"fromMe": False}}}
    assert catchup._chat_has_pending_message(chat) is True


def test_chat_has_pending_message_false_when_last_message_from_us():
    chat = {"lastMessage": {"key": {"fromMe": True}}}
    assert catchup._chat_has_pending_message(chat) is False


def test_chat_has_pending_message_false_without_last_message():
    assert catchup._chat_has_pending_message({}) is False


def _incoming_record(msg_id, ts, remote_jid="491234567@s.whatsapp.net"):
    return {
        "key": {"id": msg_id, "fromMe": False, "remoteJid": remote_jid},
        "message": {"conversation": f"msg-{msg_id}"},
        "messageTimestamp": ts,
    }


def test_catch_up_chat_processes_only_messages_newer_than_checkpoint():
    records = [_incoming_record("A", 100), _incoming_record("B", 200), _incoming_record("C", 50)]

    with patch.object(catchup.evolution_api, "find_messages", return_value=records), \
         patch.object(catchup.conversation_state, "get_or_create", return_value={"last_processed_message_ts": 100}), \
         patch.object(catchup.dialog_manager, "handle_message") as mock_handle:
        catchup._catch_up_chat("491234567@s.whatsapp.net")

    # Nur "B" (ts=200) liegt nach dem Checkpoint (100); "A" (=100) und "C" (50) nicht.
    mock_handle.assert_called_once()
    assert mock_handle.call_args[0][0] == "491234567"
    assert mock_handle.call_args[0][1]["message_id"] == "B"


def test_catch_up_chat_processes_in_chronological_order():
    records = [_incoming_record("LATER", 300), _incoming_record("EARLIER", 250)]
    processed_order = []

    def fake_handle(phone, message):
        processed_order.append(message["message_id"])

    with patch.object(catchup.evolution_api, "find_messages", return_value=records), \
         patch.object(catchup.conversation_state, "get_or_create", return_value={"last_processed_message_ts": 0}), \
         patch.object(catchup.dialog_manager, "handle_message", side_effect=fake_handle):
        catchup._catch_up_chat("491234567@s.whatsapp.net")

    assert processed_order == ["EARLIER", "LATER"]


def test_catch_up_chat_skips_outgoing_and_unparseable_records():
    records = [
        {"key": {"id": "OUT", "fromMe": True}, "message": {"conversation": "x"}, "messageTimestamp": 10},
        {"key": {"id": "EDITED", "fromMe": False}, "message": None, "messageTimestamp": 20},
        _incoming_record("REAL", 30),
    ]

    with patch.object(catchup.evolution_api, "find_messages", return_value=records), \
         patch.object(catchup.conversation_state, "get_or_create", return_value={"last_processed_message_ts": 0}), \
         patch.object(catchup.dialog_manager, "handle_message") as mock_handle:
        catchup._catch_up_chat("491234567@s.whatsapp.net")

    mock_handle.assert_called_once()
    assert mock_handle.call_args[0][1]["message_id"] == "REAL"


def test_catch_up_chat_stops_on_processing_error_without_crashing():
    records = [_incoming_record("A", 100), _incoming_record("B", 200)]

    with patch.object(catchup.evolution_api, "find_messages", return_value=records), \
         patch.object(catchup.conversation_state, "get_or_create", return_value={"last_processed_message_ts": 0}), \
         patch.object(catchup.dialog_manager, "handle_message", side_effect=RuntimeError("boom")):
        catchup._catch_up_chat("491234567@s.whatsapp.net")  # muss NICHT crashen


def test_check_missed_messages_only_scans_pending_chats():
    chats = [
        {"remoteJid": "491234567@s.whatsapp.net", "lastMessage": {"key": {"fromMe": False}}},
        {"remoteJid": "497654321@s.whatsapp.net", "lastMessage": {"key": {"fromMe": True}}},
        {"remoteJid": "123-456@g.us", "lastMessage": {"key": {"fromMe": False}}},
    ]

    with patch.object(catchup.evolution_api, "find_chats", return_value=chats), \
         patch.object(catchup, "_catch_up_chat") as mock_catch_up:
        catchup.check_missed_messages()

    mock_catch_up.assert_called_once_with("491234567@s.whatsapp.net")


def test_check_missed_messages_handles_find_chats_failure_gracefully():
    with patch.object(catchup.evolution_api, "find_chats", side_effect=RuntimeError("boom")), \
         patch.object(catchup, "_catch_up_chat") as mock_catch_up:
        catchup.check_missed_messages()  # muss NICHT crashen
    mock_catch_up.assert_not_called()


def test_run_after_reconnect_noop_when_disabled():
    with patch.object(catchup.Config, "ENABLE_CATCHUP_SYNC", False), \
         patch("threading.Thread") as mock_thread:
        catchup.run_after_reconnect()
    mock_thread.assert_not_called()


def test_run_after_reconnect_respects_cooldown():
    # Erster Lauf lange nach _last_run_at=0.0 -> darf durch. Zweiter Lauf nur
    # 1 Sekunde spaeter, bei einem Cooldown von 60s -> muss blockiert werden.
    catchup._last_run_at = 0.0
    with patch.object(catchup.Config, "ENABLE_CATCHUP_SYNC", True), \
         patch.object(catchup.Config, "CATCHUP_MIN_INTERVAL_SECONDS", 60), \
         patch.object(catchup.time, "monotonic", side_effect=[1_000_000.0, 1_000_001.0]), \
         patch("threading.Thread") as mock_thread:
        catchup.run_after_reconnect()
        first_call_count = mock_thread.call_count
        catchup.run_after_reconnect()

    assert first_call_count == 1
    assert mock_thread.call_count == 1  # zweiter Aufruf wurde durch Cooldown blockiert
