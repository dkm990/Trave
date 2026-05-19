# Telegram smoke-test (live)

Этот документ — пошаговый чек-лист, чтобы прогнать MVP в реальном Telegram. Без него считаем «ничего не проверено в живой системе».

## 0. Пререквизиты

- Python 3.11+ (проверено на 3.14)
- Node.js 18+
- Аккаунт Telegram
- `cloudflared` или `ngrok`, или `localtunnel` для HTTPS-туннеля

## 1. Создать бота через BotFather

1. Открой [@BotFather](https://t.me/BotFather) → `/newbot`.
2. Имя: любое, например `Yo travel demo`.
3. Username: должен заканчиваться на `bot`, например `yo_travel_demo_bot`.
4. Скопируй полученный `BOT_TOKEN` — выглядит как `1234567890:AA...`.
5. Включи (оставь по умолчанию) приватный режим в группах:
   `/setprivacy` → выбрать бота → **Enable**.
   Это ключевой пункт: бот в группах будет видеть только свои команды,
   reply на себя и упоминания. Без этого бот будет читать весь чат.
6. (опционально) Иконка/описание: `/setdescription`, `/setuserpic`.

> Mini App URL у BotFather задаём после того, как поднимем туннель (шаг 5).

## 2. Подготовить .env

```cmd
cd E:\Projects\Yo\backend
copy .env.example .env
```

Открой `backend/.env` и поставь как минимум:

```
BOT_TOKEN=1234567890:AA...                     # из шага 1
TELEGRAM_BOT_USERNAME=yo_travel_demo_bot       # без @
DEV_ALLOW_INSECURE_AUTH=1
DATABASE_URL=sqlite+aiosqlite:///./yo.db
WEBAPP_URL=                                    # заполним на шаге 5
```

Переменные `BOT_TOKEN` и `TELEGRAM_BOT_TOKEN` взаимозаменяемые. То же для `WEBAPP_URL` и `MINI_APP_URL`. Backend ничего не выводит в логах из секретов — будет только флаг `bot_token=set`.

Frontend env:
```cmd
cd E:\Projects\Yo\frontend
copy .env.example .env
```
По умолчанию `VITE_API_BASE_URL=http://localhost:8000`. Менять не нужно.

## 3. Запустить backend API

```cmd
cd E:\Projects\Yo\backend
.\.venv\Scripts\activate
python -m pip install -r requirements.txt   # если venv ещё не создан
uvicorn app.main:app --reload --port 8000
```

В логах должна появиться сводка вида:
```
== Yo api startup ==
env=dev
database: sqlite (sqlite+aiosqlite:///./yo.db)
telegram: bot_token=set bot_username=set mini_app=MISSING (https tunnel?)
auth: dev_allow_insecure=True (DO NOT USE IN PROD)
currency: frankfurter base=RUB ttl=12h
ai: provider=rule_based
```

Открой `http://localhost:8000/health` — `{"status":"ok"}`. Открой `http://localhost:8000/diagnostics` — JSON без секретов.

## 4. Запустить bot (long polling)

В отдельном терминале:
```cmd
cd E:\Projects\Yo\backend
.\.venv\Scripts\activate
python run_bot.py
```

Должно быть `Bot @yo_travel_demo_bot started in polling mode`.

## 5. Запустить frontend и поднять HTTPS-туннель

В третьем терминале:
```cmd
cd E:\Projects\Yo\frontend
npm install
npm run dev
```

Откроется на `http://localhost:5173`.

В четвёртом терминале — туннель:

```cmd
cloudflared tunnel --url http://localhost:5173
```
Получишь HTTPS URL вида `https://something-random.trycloudflare.com`.

Альтернатива: `npx localtunnel --port 5173` или `ngrok http 5173`.

Этот URL поставь:
1. В `backend/.env` → `WEBAPP_URL=https://something-random.trycloudflare.com`. **Перезапусти backend и bot.**
2. У BotFather:
   - `/setdomain` → выбрать бота → ввести домен туннеля без https.
   - `/setmenubutton` → выбрать бота → текст «Открыть Yo» → URL туннеля. Это даёт кнопку Mini App в меню чата.
   - Альтернатива: `/newapp` → создать Web App с тем же URL.

## 6. Сценарий проверки в личном чате

Открой бота в Telegram и пройди по списку:

| Шаг | Действие | Ожидание |
|-----|----------|----------|
| 1 | `/start` | Приветствие + кнопка «Открыть Mini App» |
| 2 | Нажать кнопку Mini App | Открывается экран Поездки |
| 3 | `/newtrip Vietnam demo` | Поездка создана, id показан |
| 4 | `/trips` | Список содержит «Vietnam demo» |
| 5 | `/rate 100 USD RUB` | Сумма + курс + дата + источник |
| 6 | Прислать PDF/картинку | Кнопки выбора типа документа |
| 7 | Выбрать «Билет» | «Сохранено в поездке…» |
| 8 | `/docs` | Видна запись с типом «ticket» |
| 9 | `/docs hotel` | Если совпадений нет — «Документов нет.» |
| 10 | `/balance` | «Расходов пока нет.» (новая поездка) |
| 11 | `/add 100 THB Coffee` | Подтверждение «Понял: 100 THB, Coffee, оплатил…» с кнопками Да/Изменить/Отмена |
| 12 | Нажать «Да» | «✅ Расход добавлен: 100 THB ≈ ... RUB (Coffee)» |
| 13 | `/balance` | Видим себя с net = 0 (заплатил = доля) |

## 7. Сценарий проверки в группе

1. Создай тестовую группу, добавь туда бота.
2. В группе:

| Шаг | Действие | Ожидание |
|-----|----------|----------|
| 1 | `/newtrip Vietnam group` | «✅ Поездка создана… ℹ️ Бот не видит список участников группы — каждый должен написать /join сам» + список команд |
| 2 | Каждый участник пишет `/join` | «{Имя} добавлен в поездку…» |
| 3 | `/add 1200000 VND ресторан за всех` | Подтверждение «Понял: 1200000 VND, ресторан, оплатил {Имя}, делим на: …» |
| 4 | Кнопка «Да» | «✅ Расход добавлен» |
| 5 | `/balance` | Список с net по каждому, «кто кому должен» |
| 6 | `@yo_travel_demo_bot я оплатил такси 300000 VND за всех` | Подтверждение распознанного расхода |
| 7 | Кнопка «Да» | Расход записан |
| 8 | `/balance` | Балансы обновились |
| 9 | `/docs hotel` | Если общих документов нет — «Общих документов поездки нет. Я могу прислать твои личные в личку.» |
| 10 | `/app` | Кнопка для открытия Mini App |

## 8. Проверка Mini App

Открой Mini App из бота в Telegram (не из браузера, чтобы получить настоящий `initData`):

- **Trips**: список поездок, видны и личные, и групповые
- **Trip dashboard**: участники, баланс, кнопки
- **Expenses**: видна история расходов; добавление работает
- **Balances**: «кто кому должен», цвет positive/negative
- **Converter**: 100 USD → RUB, видна дата курса и источник
- **Documents**: список с фильтром по типу

## 9. Сценарий «выключить dev auth»

Когда базовая проверка прошла:

1. В `backend/.env`: `DEV_ALLOW_INSECURE_AUTH=0`.
2. Перезапусти backend. В логе должно стать `dev_allow_insecure=False` без warning.
3. Mini App продолжает работать **только из Telegram** (initData валиден). Открытие в обычном браузере должно давать `401 Telegram init data missing`.

## 10. Что проверять в баг-репорте

Зафиксируй: команда → ожидание → факт → лог backend/bot. Особенно:

- Бот не отвечает в группе → проверить privacy у BotFather и что бот добавлен с правами.
- Mini App не открывается → проверить `WEBAPP_URL`, что туннель жив, что у BotFather домен совпадает.
- Курс не отдаётся → `GET /api/currency/rate?base=USD&quote=RUB`. Frankfurter иногда не поддерживает экзотические пары (VND, AMD) — fallback стоит на устаревший кеш.
- Confirmation flow не работает → InlineKeyboard рассчитан только на автора расхода (см. сообщение «Подтвердить может только автор расхода»).

### `/add` vs natural language mention

Поведение **одинаковое**: оба пути показывают confirmation «Понял: …» с
кнопками Да / Изменить / Отмена. Расход пишется в БД только после «Да».

| Способ | Где работает | Что нужно |
|--------|--------------|-----------|
| `/add 1200 RUB ужин за всех` | личка и группа | Прямая команда; парсится тем же rule_based parser |
| `я оплатил такси 300000 VND за всех` | только в группе через mention `@{bot}` или reply на бота | Текст должен содержать verb («оплатил/заплатил») или явное `делим на N` |

**Деньги без подтверждения никогда не пишутся.** Если в будущем хочется
«быстрой записи» без кнопки — это явный TODO, требующий отдельного флага
у пользователя.

## 11. Currency provider chain

В MVP подключены два бесплатных провайдера без API ключей:

- **frankfurter** — primary, поддерживает USD, EUR, RUB, THB, CNY, JPY, GBP и около 30 ECB-валют. **Не поддерживает** VND, AMD, KZT, BYN, GEL — для них автоматически идёт fallback.
- **exchangerate_open** — fallback ([open.er-api.com](https://open.er-api.com/v6/latest/USD)). Покрывает ~160 валют включая travel-валюты.

Перед live тестом полезно прогнать:
```cmd
cd E:\Projects\Yo\backend
.\.venv\Scripts\python.exe scripts\check_currency_support.py
.\.venv\Scripts\python.exe scripts\check_currency_support.py --base RUB
```
Скрипт покажет таблицу `currency | frankfurter | exchangerate_open`. Любая пара, по которой оба = error/unsupported, будет давать `CurrencyError` в боте/Mini App.

**Attribution.** ExchangeRate-API open-access требует видимую ссылку «Rates By [Exchange Rate API](https://www.exchangerate-api.com)». Не убирать при форке.

**Production guidance.** Open-access endpoint без ключа: не realtime, данные обновляются примерно раз в сутки, мы кешируем ответы, чтобы не делать лишних запросов. Возможны soft rate limits и `HTTP 429`. Если расходы пишутся часто — рекомендуется бесплатный API key на exchangerate-api.com (1.5k req/мес, без attribution) или платный план. Сейчас в `.env.example` есть `EXCHANGERATE_API_KEY=` placeholder; провайдер с ключом будет добавлен на следующем этапе.


## 12. Gemini provider (опционально)

В `.env` поставь:
```
AI_PROVIDER=gemini
AI_FALLBACK_PROVIDER=rule_based
GEMINI_API_KEY=<key from aistudio.google.com/apikey>
GEMINI_MODEL=gemini-2.5-flash
```

Перезапусти бота. В логах появится `ai: provider=gemini fallback=rule_based gemini_key=set`.

В Telegram проверь:
- `/ai ресторан 1.2кк донгов за всех` → confirmation 1 200 000 VND, food.
- `/ai я заплатил за такси 50 баксов, ехали с Зои` → confirmation 50 USD, mentioned=Зои. Если Зои нет в trip → ошибка «Не нашёл участника Зои».
- `Трейв, скинь баланс` → balance.
- `Трейв, сколько мы потратили за сегодня?` → today summary.
- Reply на сообщение бота с фразой `я оплатил кофе 100 THB за всех` → confirmation.

Что **не** должно происходить:
- Бот не должен отвечать на сообщения в группе без trigger/mention/reply (например, на «как погода?»).
- В логах bot polling не должно быть `GEMINI_API_KEY` или полного текста сообщения — только `intent_router chat=... user=... provider=... intent=... confidence=...`.

**Безопасность.** Gemini получает только сообщения, явно адресованные боту:
slash-команды, mention `@bot`, reply на бота, trigger words `Трейв,` /
`TravelBot` / `бот,`. Весь чат **не** отправляется в Gemini, даже если
privacy mode выключен.
