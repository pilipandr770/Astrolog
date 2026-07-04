"""
Транскрипция голосовых сообщений через OpenAI Whisper.

Основной путь — transcribe_from_base64(): Evolution API отдаёт голосовое
уже РАСШИФРОВАННЫМ через /chat/getBase64FromMediaMessage (см.
evolution_api.get_media_base64). Скачивать по URL из вебхука нельзя —
там лежит E2E-зашифрованный файл WhatsApp (mmg.whatsapp.net/...enc),
OpenAI отвечает на него 'Invalid file format' (проверено на проде).

TODO при WHISPER_MODE=local: подключить faster-whisper, дешевле при
большом объёме звонков, но требует ресурсов на VPS (CPU/GPU).
"""
import base64
import io

import requests
from openai import OpenAI
from app.config import Config

_client = None


def _get_client() -> OpenAI:
    # Lazy statt Modul-Level-Instanziierung: die OpenAI-SDK wirft beim
    # Erstellen einen Fehler, wenn kein API-Key gesetzt ist — das würde
    # sonst schon beim Import dieses Moduls die ganze App zum Absturz
    # bringen (auch wenn gerade keine Sprachnachricht verarbeitet wird).
    global _client
    if _client is None:
        _client = OpenAI(api_key=Config.OPENAI_API_KEY)
    return _client


def _ext_from_mimetype(mimetype: str | None) -> str:
    """
    WhatsApp-Sprachnachrichten kommen als 'audio/ogg; codecs=opus' —
    OpenAI bestimmt das Format über den Dateinamen, daher hier die
    passende Endung wählen. Unbekannte Typen fallen auf ogg zurück
    (das Standardformat von WhatsApp-Voice).
    """
    if not mimetype:
        return "ogg"
    base = mimetype.split(";")[0].strip().lower()
    return {
        "audio/ogg": "ogg",
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/mp4": "m4a",
        "audio/m4a": "m4a",
        "audio/aac": "m4a",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/webm": "webm",
        "audio/flac": "flac",
    }.get(base, "ogg")


def _transcribe_file(audio_file) -> dict:
    """
    Возвращает {"text": ..., "language": ...} — language НЕ задаётся заранее
    (никакого захардкоженного "de"), а определяется Whisper автоматически
    (response_format="verbose_json" отдаёт его в ответе, полное название
    вроде "german"/"english"/"russian"). Используется в dialog_manager.py
    как сигнал языка для генерации тизера/отчёта на языке пользователя
    (см. claude_service._language_directive()).
    """
    if Config.WHISPER_MODE == "local":
        raise NotImplementedError(
            "WHISPER_MODE=local не реализован. Подключи faster-whisper здесь."
        )

    transcript = _get_client().audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        response_format="verbose_json",
    )
    return {"text": transcript.text, "language": getattr(transcript, "language", None)}


def transcribe_from_base64(b64_data: str, mimetype: str | None = None) -> dict:
    """
    Транскрибирует голосовое из base64 — то, что отдаёт
    evolution_api.get_media_base64() (уже расшифрованный медиафайл).
    """
    audio_bytes = base64.b64decode(b64_data)
    audio_file = io.BytesIO(audio_bytes)
    # OpenAI SDK ждёт файлоподобный объект с именем (для определения формата)
    audio_file.name = f"voice.{_ext_from_mimetype(mimetype)}"
    return _transcribe_file(audio_file)


def transcribe_from_url(media_url: str) -> dict:
    """
    Скачивает голосовое по прямой (НЕзашифрованной) ссылке и транскрибирует.
    Для вебхуков Evolution НЕ подходит (URL там зашифрованная) — используй
    transcribe_from_base64(). Оставлено для прямых ссылок/тестов.
    """
    audio_response = requests.get(media_url, timeout=30)
    audio_response.raise_for_status()

    audio_file = io.BytesIO(audio_response.content)
    audio_file.name = "voice.ogg"
    return _transcribe_file(audio_file)
