"""
Транскрипция голосовых сообщений. ЗАГЛУШКА — рабочая логика для
WHISPER_MODE=api, но не протестирована end-to-end с реальным медиафайлом
от Evolution API (нужно проверить формат, в котором Evolution отдаёт
голосовые — обычно .ogg/opus, OpenAI API это ест напрямую).

TODO при WHISPER_MODE=local: подключить faster-whisper, дешевле при
большом объёме звонков, но требует ресурсов на VPS (CPU/GPU).
"""
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


def transcribe_from_url(media_url: str) -> dict:
    """
    Скачивает голосовое по URL из вебхука Evolution API и транскрибирует.

    Возвращает {"text": ..., "language": ...} — language НЕ задаётся заранее
    (никакого захардкоженного "de"), а определяется Whisper автоматически
    (response_format="verbose_json" отдаёт его в ответе, полное название
    вроде "german"/"english"/"russian"). Используется в dialog_manager.py
    как сигнал языка для генерации тизера/отчёта на языке пользователя
    (см. claude_service._language_directive()).
    """
    audio_response = requests.get(media_url, timeout=30)
    audio_response.raise_for_status()

    # OpenAI SDK ждёт файлоподобный объект с именем (для определения формата)
    import io
    audio_file = io.BytesIO(audio_response.content)
    audio_file.name = "voice.ogg"

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
