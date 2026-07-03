# WhatsApp Astrologer Bot (Lal Kitab)

> Этот README — точка входа для Claude Code. Прочитай его целиком перед тем, как
> что-либо менять. Он описывает цель, архитектуру, текущее состояние и то,
> что осталось сделать.

## Цель проекта

WhatsApp-бот, который:

1. Общается с пользователем в WhatsApp (текст и голосовые сообщения).
2. Собирает дату, время и место рождения (диалогом, с уточняющими вопросами).
3. Рассчитывает натальную карту программно (Swiss Ephemeris, сидерический
   зодиак, аянамша Lahiri — стандарт для ведической/Lal Kitab традиции).
4. Применяет к рассчитанным позициям правила книги **Лал Китаб** (rin —
   "долги" планет, спящие/пробуждённые дома, специфичные для Лал Китаб
   комбинации — это НЕ классическая джйотиш-интерпретация).
5. Генерирует толкование текстом через Claude (Anthropic API).
6. Верстает результат в красивый PDF.
7. Отправляет PDF пользователю обратно в WhatsApp.
8. Монетизация — оплата через Stripe перед генерацией отчёта.

Технически бот работает через **Evolution API** (self-hosted инстанс на
Hostinger) — вебхуки приходят на Flask-приложение, ответы уходят обратно
через Evolution API HTTP-клиент.

## Статус: это СКЕЛЕТ, не готовый продукт

Что уже реально работает и протестировано:

- ✅ Расчёт сидерических позиций планет через `pyswisseph` (Lahiri аянамша) —
  проверено, даёт корректные градусы. См. `app/services/ephemeris.py`.
- ✅ Структура Flask-приложения, роутинг, конфиг через `.env`.
- ✅ Заготовка диалоговой state machine (SQLite) для сбора данных рождения.
- ✅ Шаблон PDF на Jinja2 + WeasyPrint, рендерится в файл.
- ✅ Клиент для Evolution API (отправка текста и документов) — сигнатуры
  методов совпадают с типовым Evolution API v2, **но не протестированы
  против реального инстанса** — проверь версию своего контейнера на
  Hostinger, эндпоинты могли отличаться.

Что НЕ сделано / затронуто только заглушками:

- ❌ **Правила Лал Китаб** (`app/services/lal_kitab.py`) — самое важное и
  самое трудоёмкое место. Сейчас там только структура данных и 2-3 примера
  правил как образец. Реальный набор правил нужно переносить из первоисточника
  вручную — единого правильного open-source датасета правил Лал Китаб я не
  нашёл, придётся кодировать самостоятельно. См. `docs/LAL_KITAB_NOTES.md`.
- ❌ Whisper-транскрипция (`app/services/whisper_service.py`) — заглушка,
  нужно подставить реальный API-ключ и решить: OpenAI Whisper API или
  self-hosted `faster-whisper` (дешевле при большом объёме).
- ❌ Генерация интерпретации через Claude (`app/services/claude_service.py`) —
  структура промпта есть, но не финализирована и не тестировалась на реальных
  расчётах.
- ❌ Геокодинг + историческая таймзона (`app/services/geocoding.py`) —
  подключены библиотеки, но нет ключа для геокодинг-провайдера.
- ❌ Stripe (`app/services/stripe_service.py`) — Checkout Session создаётся,
  но webhook-обработчик не подключен к реальному флоу генерации отчёта.
- ❌ Реальный диалоговый флоу в `app/routes/webhook.py` — сейчас просто
  echo-заглушка, чтобы показать, куда что подключать.
- ❌ Файлы эфемерид Swiss Ephemeris (`ephe/`) — папка пустая, нужно скачать
  `.se1` файлы с astro.com (см. TODO.md), иначе `pyswisseph` упадёт в
  Moshier-режим (менее точный).

## Структура проекта

```
whatsapp-astrologer-bot/
├── run.py                          # точка входа
├── requirements.txt
├── .env.example                    # скопировать в .env и заполнить
├── app/
│   ├── config.py                   # конфиг из переменных окружения
│   ├── db.py                       # SQLite init
│   ├── routes/
│   │   ├── webhook.py              # приём сообщений от Evolution API
│   │   └── stripe_webhook.py       # приём событий от Stripe
│   ├── services/
│   │   ├── evolution_api.py        # отправка сообщений/документов в WhatsApp
│   │   ├── whisper_service.py      # голос -> текст (ЗАГЛУШКА)
│   │   ├── ephemeris.py            # расчёт позиций планет (РАБОТАЕТ)
│   │   ├── lal_kitab.py            # правила Лал Китаб (ЗАГЛУШКА, основной TODO)
│   │   ├── claude_service.py       # генерация толкования через Claude
│   │   ├── pdf_generator.py        # рендер PDF из HTML-шаблона
│   │   ├── stripe_service.py       # Checkout Session
│   │   └── geocoding.py            # место рождения -> координаты + TZ
│   ├── models/
│   │   └── conversation_state.py   # state machine диалога (SQLite)
│   └── templates/
│       └── report.html             # шаблон PDF-отчёта
├── docs/
│   ├── ARCHITECTURE.md             # схема потока данных подробно
│   ├── LAL_KITAB_NOTES.md          # что именно нужно закодировать
│   └── TODO.md                     # приоритизированный список задач
└── tests/
    └── test_ephemeris.py           # smoke-тест расчёта (проходит)
```

## Быстрый старт

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# заполни .env: ANTHROPIC_API_KEY, EVOLUTION_API_URL, EVOLUTION_API_KEY,
# STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, OPENAI_API_KEY (для Whisper)

python3 run.py
```

Smoke-тест эфемерид (не требует .env):

```bash
python3 -m pytest tests/ -v
```

## Деплой на VPS через Docker (без домена)

Проект рассчитан на деплой рядом с self-hosted Evolution API на одном VPS,
без покупки домена — подтверждение оплаты Stripe идёт через polling (см.
`app/services/payment_poller.py` и `docs/ARCHITECTURE.md`), а не вебхук.

```bash
cp .env.example .env   # заполни ключи, включая BOT_WHATSAPP_NUMBER
docker compose up -d --build
```

Чтобы Evolution API (тоже в Docker) мог достучаться до бота:

1. Проверь, в какой docker-сети сидит контейнер Evolution API:
   `docker inspect <evolution-container> | grep -A5 Networks`
2. Подключи к этой же сети контейнер бота (или наоборот — подключи Evolution
   к сети `astrolog-net` из `docker-compose.yml`):
   `docker network connect <имя-сети> whatsapp-astrologer-bot`
3. В настройках Evolution API укажи webhook URL по имени контейнера бота:
   `http://whatsapp-astrologer-bot:5000/webhook/evolution` — так трафик не
   выходит за пределы VPS, публичный адрес не нужен.

Если панель твоего хостинга не даёт вручную объединять сети — у тебя всё
равно есть root SSH (значит, обычный `docker network connect` из терминала
сработает независимо от возможностей GUI-панели).

## Админка

Отдельный сервис `admin` (порт `ADMIN_PORT`, по умолчанию 5001), защищён
паролем (`ADMIN_PASSWORD`) и **не публикуется наружу** — в `docker-compose.yml`
привязан только к `127.0.0.1`. Доступ с локальной машины через SSH-туннель:

```bash
ssh -L 5001:localhost:5001 user@your-vps-ip
# затем открой http://localhost:5001/admin в браузере
```

Что внутри:
- **Статистика** — количество разговоров по статусам, число оплат, оценка выручки
- **Дополнительные инструкции** — текст, который добавляется к системному промпту
  Claude при каждой генерации (тизер и полный отчёт) — можно скорректировать тон,
  добавить актуальные заметки и т.п.
- **Подключение WhatsApp-номера** — ссылка на встроенный Evolution API Manager
  (там же QR-код для подключения/смены номера); свой QR-интерфейс не делали
  осознанно, чтобы не дублировать логику Evolution.

## С чего начать (порядок для Claude Code)

Рекомендуемый порядок работы — см. `docs/TODO.md` за деталями и обоснованием
приоритета каждого пункта. Коротко: сначала докрутить диалоговую логику и
Evolution API интеграцию (без этого бот не запустится вообще), потом Lal
Kitab-правила (это ядро продукта), потом Stripe и полировка PDF.
