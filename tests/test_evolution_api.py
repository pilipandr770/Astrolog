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
