# Архитектура

## Три роли Claude

Клиента ведут три разные системные роли Claude, друг за другом, без ручного
переключения — переход задаёт state machine в `conversation_state`:

1. **Продажник-маркетолог** (`claude_service.generate_sales_reply`, состояния
   `new`/`sales_chat`) — свободно отвечает на вопросы до сбора данных: честно
   объясняет расчёт (точная астрономия) vs. трактовку (признанный источник
   Лал Китаб), цену, что входит в отчёт. Сам решает через tool-call
   `start_intake`, когда пора переходить к сбору даты/времени/места.
2. **Астролог-интерпретатор** (`claude_service.generate_teaser` /
   `generate_interpretation`, весь путь от `awaiting_style` до `paid`) —
   строит карту (`natal_chart.compute`), даёт бесплatный тизер, а после
   оплаты — полный отчёт с толкованием и почасовым календарём на месяц.
3. **Астролог-коуч** (`claude_service.generate_post_report_reply`, состояние
   `report_sent`) — сопровождает клиента ПОСЛЕ отправки PDF: отвечает на
   вопросы по уже прочитанному отчёту (текст берётся из
   `conversation_state.last_interpretation`, не переинтерпretируется заново,
   чтобы не противоречить PDF), помогает применить рекомендации в жизни, с
   элементами коучинга/мотивации — но без выдуманных фактов.

Операторские данные (юр. ссылки на Datenschutz/Impressum и т.п.) НЕ
хардкодятся в промптах — задаются через админку
(`app/routes/admin.py` → `/admin/instructions`, ключ `extra_claude_instructions`
в таблице `settings`) и автоматически подмешиваются во все три роли через
`claude_service._with_extra_instructions()`.

## Поток данных (happy path)

```
Пользователь → WhatsApp → Evolution API (Hostinger)
    → POST /webhook/evolution (Flask)
    → conversation_state: определить текущий шаг диалога
    → [текст] использовать как есть
    → [голос] whisper_service.transcribe_from_url() → текст
    → new/sales_chat: свободный разговор с Claude (dialog_manager.
      _handle_sales_chat, claude_service.generate_sales_reply) — отвечает на
      вопросы, честно объясняет расчёт vs. трактовку, сам решает через
      tool-call start_intake, когда пользователь готов перейти к сбору данных
      (история диалога — conversation_state.sales_chat_history, JSON)
    → парсинг ответа, обновление conversation_state
    → когда все 3 поля собраны (дата, время, место):
        geocoding.geocode_place() → lat/lon/tz
    → awaiting_style: бот спрашивает стиль отчёта (dialog_manager._handle_style,
      claude_service.STYLE_PRESETS — warm/humorous/business/romantic,
      номером 1-4), сохраняется в conversation_state.style
    → natal_chart.compute() — единая точка расчёта карты, используется и
      тизером, и (в будущем) полным отчётом:
        geocoding.local_to_utc_datetime() → UTC-момент для эфемерид (с учётом
        возможного сдвига даты у полуночи)
        ephemeris.calculate_positions() / assign_houses()
        lal_kitab.analyze() / detect_rin() / compute_house_activation()
    → бесплатный тизер (dialog_manager._send_teaser):
        _pick_teaser_findings() выбирает 1-2 ярких находки (Moon + Sun/Jupiter)
        claude_service.generate_teaser() → короткий (~100 слов) текст с
        приглашением купить полный отчёт — на языке пользователя (см. ниже)
        и в выбранном стиле
        evolution_api.send_text() — тизер отправляется первым сообщением
    → stripe_service.create_checkout_session() → ссылка на оплату
      (success_url/cancel_url — wa.me-ссылка на бота, если APP_BASE_URL
      не задан, см. dialog_manager._payment_redirect_urls())
    → conversation_state.stripe_session_id сохраняется сразу при создании
    → evolution_api.send_text() со ссылкой (второе сообщение, после тизера)

Пользователь платит в Stripe Checkout
    → payment_poller.py (фоновый поток, опрос раз в
      Config.PAYMENT_POLL_INTERVAL_SECONDS) находит все разговоры в
      состоянии awaiting_payment и спрашивает Stripe:
      stripe_service.get_payment_status(session_id)
    → как только payment_status == "paid":
        conversation_state.update(paid=1, state="paid")
        evolution_api.send_text() — уведомление о получении оплаты
    → [TODO] триггер генерации отчёта:
        ephemeris.calculate_positions() → позиции планет
        ephemeris.assign_houses() → дома
        lal_kitab.analyze() / detect_rin() / compute_house_activation()
        claude_service.generate_interpretation() → текст толкования
        pdf_generator.generate_report_pdf() → PDF файл
        evolution_api.send_document() → отправка PDF в WhatsApp

Альтернатива (routes/stripe_webhook.py, сейчас не используется по
умолчанию): если сервер получит публичный HTTPS-адрес (домен, sslip.io,
Cloudflare Tunnel), Stripe может push'ить checkout.session.completed
вместо polling — тогда подтверждение мгновенное, а не с задержкой на
интервал опроса. Код вебхука оставлен нетронутым на этот случай.
```

## Почему так, а не иначе

- **State machine в SQLite, а не в памяти процесса** — Flask может
  перезапускаться / масштабироваться на несколько воркеров (gunicorn),
  состояние диалога должно переживать рестарт и быть общим между воркерами.
- **Сидерический зодиак (Lahiri)** — тропический зодиак (западная
  астрология) даёт другие позиции планет по знакам. Лал Китаб — часть
  ведической традиции, там принят сидерический расчёт. Если перепутать —
  все расчёты будут неверны.
- **Оплата ДО генерации отчёта** — экономит токены Claude/Whisper на
  пользователях, которые не собираются платить. Альтернатива (генерация
  до оплаты, PDF с водяным знаком как превью) тоже возможна, но дороже
  в токенах — обсуди с бизнес-стороны, какой конверсионный флоу лучше.
- **PDF через WeasyPrint (HTML/CSS), а не ReportLab напрямую** — для
  текстово-табличного отчёта HTML/CSS вёрстка быстрее итерируется и проще
  поддерживать дизайн, чем императивный API ReportLab. Если понадобится
  рисовать саму карту рождения (круг с домами и планетами как графика) —
  можно сгенерировать SVG отдельно и встроить в HTML перед рендером в PDF.
- **Многоязычность — только у гороскопа (тизер/отчёт/PDF), не у диалога
  сбора данных** — вопросы даты/времени/места и ошибки остаются на
  немецком всегда. Полный перевод всего диалога потребовал бы отдельного
  слоя переводов (i18n) для каждого шага state machine — сознательно не
  делали, чтобы не раздувать объём работы; сам гороскоп генерирует Claude,
  который и так пишет текст с нуля, поэтому "просто попроси на нужном
  языке" не требует доп. инфраструктуры.
- **Язык гороскопа определяет сам Claude, без отдельной библиотеки
  детекции** — `claude_service._language_directive()` передаёт Claude
  сырой сигнал (либо `language_hint` — язык, который явно распознал
  Whisper при транскрипции голосового, либо `language_sample` — текст
  первого сообщения пользователя) и просит ответить на том же языке,
  с фоллбэком на немецкий. Отдельная библиотека (`langdetect` и т.п.)
  не нужна — Claude и так вызывается для генерации текста, определение
  языка "бесплатно" достаётся в том же вызове.
- **Стиль отчёта — фиксированный список (`claude_service.STYLE_PRESETS`),
  не свободный текст** — через WhatsApp без кнопок проще всего попросить
  прислать номер 1-4, чем парсить произвольное описание стиля.
- **Переход из свободного чата в сбор данных — через tool-call, не через
  текстовый маркер** — `claude_service.START_INTAKE_TOOL` надёжнее, чем
  просить Claude дописать в конце спец-строку и парсить/вырезать её из
  ответа (риск утечки маркера пользователю или пропуска при перефразировании).

## Известные ограничения текущего скелета

- Нет очереди задач (Celery/RQ) — генерация отчёта после оплаты, когда
  будет подключена (TODO.md п.4), должна быть синхронным вызовом внутри
  `payment_poller.check_pending_payments()` либо тоже вынесена в отдельный
  поток/задачу, если генерация PDF + вызов Claude займёт больше нескольких
  секунд (в отличие от вебхука здесь нет жёсткого таймаута со стороны
  Stripe, но заставлять пользователя ждать несколько минут между "оплата
  прошла" и "отчёт пришёл" всё равно не стоит).
- **Payment polling вместо вебхука** (см. `app/services/payment_poller.py`)
  — подтверждение оплаты приходит с задержкой до `PAYMENT_POLL_INTERVAL_SECONDS`
  (по умолчанию 90 сек), а не мгновенно. Выбрано намеренно, чтобы не
  требовать домена/туннеля для VPS-деплоя. При gunicorn с несколькими
  workers каждый worker запустит свой поток поллера (дублирование
  сообщений!) — см. `Config.ENABLE_INPROCESS_PAYMENT_POLLER` и запуск
  `python -m app.services.payment_poller` отдельным процессом.
- Нет ретраев при сбое отправки в Evolution API или Stripe.
- Нет rate limiting на вебхуки.
- Один язык интерфейса (немецкий) захардкожен в system-промпте Claude и в
  PDF-шаблоне — если нужна мультиязычность, вынести в параметр.
