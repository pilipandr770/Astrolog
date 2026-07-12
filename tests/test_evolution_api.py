import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

from app.services import evolution_api


def test_split_text_returns_single_chunk_for_short_text():
    assert evolution_api._split_text("Hallo, wie geht's?") == ["Hallo, wie geht's?"]


def test_split_text_returns_single_chunk_for_empty_text():
    assert evolution_api._split_text("") == [""]


def test_split_text_splits_at_paragraph_boundary():
    para1 = "A" * 3000
    para2 = "B" * 3000
    text = f"{para1}\n\n{para2}"
    chunks = evolution_api._split_text(text, max_length=3500)
    assert len(chunks) == 2
    assert chunks[0] == para1
    assert chunks[1] == para2
    # Kein Chunk überschreitet das Limit.
    assert all(len(c) <= 3500 for c in chunks)


def test_split_text_splits_at_sentence_boundary_without_paragraphs():
    sentence = "Dies ist ein Satz. "
    text = sentence * 300  # deutlich über dem Limit, keine \n vorhanden
    chunks = evolution_api._split_text(text, max_length=3500)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 3500
    # Kein Satz wird mitten im Wort zerschnitten (jeder Chunk endet auf Satzzeichen
    # oder ist der letzte Rest).
    for chunk in chunks[:-1]:
        assert chunk.endswith(".")


def test_split_text_hard_cuts_when_no_separator_found():
    text = "X" * 10000  # ein einziges "Wort", keine Trennzeichen
    chunks = evolution_api._split_text(text, max_length=3500)
    assert len(chunks) == 3
    assert chunks[0] == "X" * 3500
    assert chunks[1] == "X" * 3500
    assert chunks[2] == "X" * 3000


def test_split_text_reconstructs_original_content():
    para1 = "Erster Absatz. " * 100
    para2 = "Zweiter Absatz. " * 100
    text = f"{para1}\n\n{para2}"
    chunks = evolution_api._split_text(text, max_length=500)
    # Zusammengefügt (mit den Trennern, die beim Split entfernt wurden,
    # grob wieder eingefügt) darf kein Inhalt verloren gehen.
    rejoined = "".join(chunks)
    assert rejoined.replace(" ", "").replace("\n", "") == text.replace(" ", "").replace("\n", "")


def test_send_text_sends_single_message_for_short_text():
    with patch.object(evolution_api.requests, "post") as mock_post:
        mock_post.return_value = MagicMock(json=lambda: {"ok": True})
        result = evolution_api.send_text("491234567", "Kurze Nachricht")

    assert len(result) == 1
    mock_post.assert_called_once()
    sent_payload = mock_post.call_args.kwargs["json"]
    assert sent_payload == {"number": "491234567", "text": "Kurze Nachricht"}


def test_send_text_sends_multiple_sequential_messages_for_long_text():
    long_text = ("Das ist ein langer Absatz mit vielen Woertern. " * 200) + "\n\n" + (
        "Und noch ein zweiter Absatz. " * 200
    )

    with patch.object(evolution_api.requests, "post") as mock_post:
        mock_post.return_value = MagicMock(json=lambda: {"ok": True})
        result = evolution_api.send_text("491234567", long_text)

    assert len(result) > 1
    assert mock_post.call_count == len(result)
    # Jeder gesendete Chunk bleibt unter dem Limit.
    for call in mock_post.call_args_list:
        assert len(call.kwargs["json"]["text"]) <= evolution_api.MAX_TEXT_LENGTH
        assert call.kwargs["json"]["number"] == "491234567"


def _webhook_payload(
    message, from_me=False, remote_jid="491234567@s.whatsapp.net",
    remote_jid_alt=None, message_id="MSG1", timestamp=1234567890,
):
    key = {"remoteJid": remote_jid, "fromMe": from_me, "id": message_id}
    if remote_jid_alt:
        key["remoteJidAlt"] = remote_jid_alt
    return {"data": {"key": key, "message": message, "messageTimestamp": timestamp}}


def test_extract_incoming_message_parses_text():
    payload = _webhook_payload({"conversation": "Hallo!"})
    result = evolution_api.extract_incoming_message(payload)
    assert result == {
        "phone": "491234567", "type": "text", "content": "Hallo!",
        "message_id": "MSG1", "timestamp": 1234567890,
    }


def test_extract_incoming_message_parses_audio():
    payload = _webhook_payload({"audioMessage": {"url": "https://mmg.whatsapp.net/xyz.enc"}})
    result = evolution_api.extract_incoming_message(payload)
    assert result["phone"] == "491234567"
    assert result["type"] == "audio"
    assert result["media_url"] == "https://mmg.whatsapp.net/xyz.enc"
    assert result["message_key"]["remoteJid"] == "491234567@s.whatsapp.net"
    assert result["message_id"] == "MSG1"
    assert result["timestamp"] == 1234567890


def test_extract_incoming_message_ignores_own_outgoing_echo():
    # Evolution schickt messages.upsert auch fuer die eigenen ausgehenden
    # Nachrichten des Bots (fromMe=True) -- die duerfen NICHT als
    # Nutzer-Input verarbeitet werden.
    payload = _webhook_payload({"conversation": "Danke fuer deine Zahlung!"}, from_me=True)
    assert evolution_api.extract_incoming_message(payload) is None


def test_extract_incoming_message_returns_none_for_unknown_type():
    payload = _webhook_payload({"someOtherMessageType": {"foo": "bar"}})
    assert evolution_api.extract_incoming_message(payload) is None


def test_extract_incoming_message_handles_malformed_payload_gracefully():
    assert evolution_api.extract_incoming_message({}) is None
    assert evolution_api.extract_incoming_message({"data": None}) is None


def test_extract_incoming_message_handles_edited_or_deleted_message():
    # WhatsApp "editiert"/"fuer alle geloescht" -> Evolution speichert
    # message=None fuer den Verlauf -- darf nicht mit TypeError crashen.
    payload = _webhook_payload(None)
    assert evolution_api.extract_incoming_message(payload) is None


def test_extract_incoming_message_prefers_remote_jid_alt():
    # LID-adressierte Nachrichten ("...@lid") tragen die echte
    # Telefonnummer-JID in remoteJidAlt -- die MUSS bevorzugt werden, sonst
    # landet die Nachricht faelschlich unter einer neuen "Nummer" (der LID),
    # statt beim bestehenden Kontakt.
    payload = _webhook_payload(
        {"conversation": "Hallo!"},
        remote_jid="33457828802813@lid",
        remote_jid_alt="380635071639@s.whatsapp.net",
    )
    result = evolution_api.extract_incoming_message(payload)
    assert result["phone"] == "380635071639"


def test_find_chats_returns_list_from_various_response_shapes():
    with patch.object(evolution_api.requests, "post") as mock_post:
        mock_post.return_value = MagicMock(json=lambda: [{"remoteJid": "a@s.whatsapp.net"}])
        assert evolution_api.find_chats() == [{"remoteJid": "a@s.whatsapp.net"}]

    with patch.object(evolution_api.requests, "post") as mock_post:
        mock_post.return_value = MagicMock(json=lambda: {"chats": [{"remoteJid": "b@s.whatsapp.net"}]})
        assert evolution_api.find_chats() == [{"remoteJid": "b@s.whatsapp.net"}]

    with patch.object(evolution_api.requests, "post") as mock_post:
        mock_post.return_value = MagicMock(json=lambda: {})
        assert evolution_api.find_chats() == []


def test_find_messages_returns_records():
    fake_response = {"messages": {"records": [{"key": {"id": "1"}}]}}
    with patch.object(evolution_api.requests, "post") as mock_post:
        mock_post.return_value = MagicMock(json=lambda: fake_response)
        result = evolution_api.find_messages("491234567@s.whatsapp.net")

    assert result == [{"key": {"id": "1"}}]
    sent_payload = mock_post.call_args.kwargs["json"]
    assert sent_payload["where"]["key"]["remoteJid"] == "491234567@s.whatsapp.net"


def test_find_messages_returns_empty_list_for_missing_records():
    with patch.object(evolution_api.requests, "post") as mock_post:
        mock_post.return_value = MagicMock(json=lambda: {"messages": {}})
        assert evolution_api.find_messages("491234567@s.whatsapp.net") == []
