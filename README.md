# Yo · Telegram Travel Mini App + Bot

Помощник в групповых поездках: расходы, валюты, документы. Backend на FastAPI + aiogram3, фронт — React + Vite Mini App.

## Что есть в MVP

- Telegram bot для личного чата и групп (long polling).
- Telegram Mini App: поездки, расходы, балансы, конвертер, документы.
- Конвертер валют: Frankfurter v2 + кеш в БД.
- Групповые расходы с делением поровну, normalize в base currency поездки.
- Хранилище НЕчувствительных travel-документов через `file_id` (без скачивания на сервер).
- Rule-based парсер русских/английских фраз о расходах. Опционально Ollama provider.
- Подтверждение перед записью расхода через AI.

## Жесткие границы

- Нет платных API. Используется только бесплатный Frankfurter.
- Нет хранения паспортов/виз/ID. Попытка сохранить такой документ — отказ.
- Документы храним только как `telegram_file_id` + metadata. Файлы не скачиваются.
- Бот в группах реагирует только на команды/упоминания/reply.
- Все секреты в `.env` (см. `backend/.env.example`, `frontend/.env.example`).

## Структура

```
backend/   FastAPI + aiogram3 + SQLAlchemy + Alembic
frontend/  React + Vite Mini App
docs/      План реализации, гайды по деплою
docker-compose.yml             Production-стек: api + bot + frontend + Caddy
docker-compose.postgres.yml    Override для Postgres вместо SQLite
Caddyfile                      Reverse proxy + автоматический Let's Encrypt
```

## Деплой на VPS

См. [docs/deploy-vps.md](docs/deploy-vps.md). Коротко:

```bash
cp .env.example .env                 # MINI_APP_DOMAIN=yo.example.com
cp backend/.env.example backend/.env # BOT_TOKEN, GEMINI_API_KEY и т.п.
docker compose up -d --build
```

Caddy сам выпустит TLS-сертификат, проксирует `/api/*` на backend и отдаёт SPA. Бот в long-polling — webhook не нужен.

## Установка

### Backend

```cmd
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Заполни в `backend/.env`:
- `TELEGRAM_BOT_TOKEN` — получить у [@BotFather](https://t.me/BotFather).
- `TELEGRAM_BOT_USERNAME` — username бота без `@`.
- `MINI_APP_URL` — публичный HTTPS URL Mini App. Для локальной разработки используй туннель (`cloudflared tunnel --url http://localhost:5173`, ngrok и т.п.).

Создание Telegram-бота:
1. `/newbot` у @BotFather → получи токен.
2. `/setprivacy` → оставь `Enable` (бот в группах будет реагировать только на команды/упоминания/reply).
3. `/setdomain` → укажи домен Mini App.
4. `/newapp` или `/setmenubutton` → задай Mini App URL.

#### База данных

По умолчанию SQLite (`./yo.db`). Таблицы создаются автоматически при первом запуске.

Опционально Postgres через docker:

```cmd
docker compose up -d postgres
```

И в `.env`:
```
DATABASE_URL=postgresql+asyncpg://yo:yo@localhost:5432/yo
```

Alembic подготовлен — добавить миграцию:

```cmd
alembic revision --autogenerate -m "init"
alembic upgrade head
```

#### Запуск backend

API:
```cmd
uvicorn app.main:app --reload --port 8000
```

Бот (long polling, в отдельном терминале):
```cmd
python run_bot.py
```

#### Тесты

```cmd
pytest
```

### Frontend (Mini App)

```cmd
cd frontend
npm install
copy .env.example .env
npm run dev
```

Откроется на `http://localhost:5173`. Vite проксирует `/api/*` на `http://localhost:8000`.

Production-build:
```cmd
npm run build
```
И раздавай `frontend/dist/*` через любой CDN/статик-хост, проставь `MINI_APP_URL` в backend.

## Currency

- **Primary**: [Frankfurter v2](https://www.frankfurter.app/) — бесплатный, без ключа, ECB-based. Поддерживает ~30 валют (USD, EUR, RUB, GBP, JPY, THB, CNY, …) — но НЕ VND, AMD, KZT, BYN, GEL.
- **Fallback**: [ExchangeRate-API Open Access](https://www.exchangerate-api.com/docs/free) — бесплатный, без ключа, требует attribution. Endpoint не realtime: данные обновляются примерно раз в сутки, мы кешируем ответы. Возможны soft rate limits и `HTTP 429` при злоупотреблении. Покрывает ~160 валют, включая VND, KZT, AMD, BYN, GEL, UAH.

**Attribution** (требование лицензии ExchangeRate-API):

> Rates By [Exchange Rate API](https://www.exchangerate-api.com)

Если форкаешь продукт под свой бренд, не убирай эту ссылку. Имя провайдера сохраняется в `ExchangeRateCache.provider`.

Чейн при запросе курса:
1. Свежий кеш (TTL `CURRENCY_CACHE_TTL_HOURS`).
2. Frankfurter (если пара поддерживается ECB).
3. ExchangeRate-Open (fallback).
4. Устаревший кеш (любой возраст).
5. `CurrencyError` с понятным текстом.

Все внешние запросы имеют timeout 10s.

Для production советуем:
- Получить бесплатный API key на [exchangerate-api.com](https://www.exchangerate-api.com/) (1500 req/мес без attribution) или платный pro-план.
- Прогреть кеш для основных пар поездки сразу после её создания.

Скрипт проверки покрытия:

```cmd
.\.venv\Scripts\python.exe scripts\check_currency_support.py
.\.venv\Scripts\python.exe scripts\check_currency_support.py --base RUB
```

## AI / NLP

В проекте подключены три провайдера через единый интерфейс `AIProvider`:

| Provider | Когда используется | Зависимость |
|----------|-------------------|-------------|
| `rule_based` (default) | Bullet-proof fallback. Понимает фразы про expense / show_balance / show_today_spending / convert_currency / find_document. | Нет |
| `gemini` | Если `AI_PROVIDER=gemini` и `GEMINI_API_KEY` задан. Используется только как **intent parser** — возвращает structured JSON, ничего не выполняет. | `google-genai` |
| `ollama` | Локальная LLM. | Установленный Ollama сервер |

**Как включить Gemini**:

```env
AI_PROVIDER=gemini
GEMINI_API_KEY=<your-key>
GEMINI_MODEL=gemini-2.5-flash
GEMINI_TIMEOUT_SECONDS=8
GEMINI_RETRY_COUNT=1
AI_FALLBACK_PROVIDER=rule_based
```

Бесплатный API key — [aistudio.google.com](https://aistudio.google.com/apikey).

**Безопасность**:
- Gemini получает только конкретные сообщения, **адресованные боту** (slash-команды, mention, reply, trigger words). **Весь групповой чат не отправляется** даже при выключенном privacy mode.
- `GEMINI_API_KEY` не появляется в логах и в `/diagnostics` (только bool флаг).
- `add_expense` всегда требует подтверждения Да / Изменить / Отмена.
- При timeout (8s), 429, 5xx, network error, invalid JSON — один retry, затем fallback на `rule_based`.

**Что Gemini понимает** (примеры):

- `ресторан 1.2кк донгов за всех` → add_expense, 1200000 VND, food, split_scope=all
- `я заплатил за такси 50 баксов, ехали с Зои` → add_expense, 50 USD, taxi, split_scope=mentioned, participant_names=["Зои"]
- `скинь баланс` / `кто кому должен` → show_balance
- `сколько мы потратили за сегодня` → show_today_spending

Rule-based parser тоже умеет: `1.2кк → 1200000`, `50k`, `2 кк`, баксы/донги/лари/бат, `VN D`/`US D`/`GE L` (mobile typo).

### Триггеры в группе

При **включённом** privacy mode бот видит только:
- slash-команды
- mention `@bot_username`
- reply на сообщение бота

При **выключенном** privacy mode дополнительно срабатывают **trigger words** в начале сообщения: `Трейв,`, `Тревел`, `TravelBot`, `Travel`, `Yo`, `бот,`, `bot,`. Без trigger обычный группового чат игнорируется — Gemini в него не уходит.

## Legacy: Ollama

По умолчанию `AI_PROVIDER=rule_based`. Внешних зависимостей нет. Парсер понимает фразы вида:

- «я оплатил ужин 1200 рублей за всех»
- «Антон заплатил 300 usd за отель за меня и Настю»
- «такси 30 GEL делим на троих»
- «конвертируй 100 USD в RUB»
- «кто кому должен»

Опционально включить локальную LLM через Ollama:

```
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

Если Ollama недоступна, провайдер откатывается на rule-based, приложение не падает.

## Безопасность Telegram Mini App

В `app/auth/telegram_auth.py` реализована полная HMAC-проверка `initData` по секрету бота. В dev-режиме разрешён fallback по заголовку `X-Telegram-User-Id` (флаг `DEV_ALLOW_INSECURE_AUTH=1`). В production выставь `DEV_ALLOW_INSECURE_AUTH=0`.

## Команды бота

Личный чат:
- `/start` — приветствие, кнопка Mini App.
- `/help` — справка.
- `/newtrip Название` — создать поездку.
- `/trips` — список поездок.
- `/app` — открыть Mini App.
- `/rate 100 USD RUB` — конвертация валют.
- Отправить файл боту — мастер сохранения как документа поездки.
- `/docs` или `/docs hotel` — найти документы.
- `/balance` — баланс по активной поездке.
- `/add 1200 RUB ужин за всех` — добавить расход. Бот покажет подтверждение
  «Понял: …» с кнопками Да / Изменить / Отмена; запись в БД только после
  «Да». Это поведение одинаковое для `/add` и для natural language mention
  в группе — **деньги без подтверждения не пишутся.**

Группа (бот реагирует только на команды/упоминания/reply):
- `/newtrip Название` — создать поездку для группы.
- `/bindtrip TRIP_ID` — привязать существующую поездку к группе.
- `/join` — добавиться в участники.
- `/balance` — кто кому должен.
- `/docs hotel` — найти общий документ. Личные документы пересылаются в личку.
- `@bot такси 30 GEL делим на троих` — распознать расход и подтвердить.

## API endpoints

- `POST /api/telegram/webhook` — заглушка для webhook-режима (по умолчанию используем polling).
- `GET /api/trips`, `POST /api/trips`, `GET /api/trips/{id}`
- `GET /api/trips/{id}/expenses`, `POST /api/trips/{id}/expenses`
- `GET /api/trips/{id}/balances`
- `GET /api/trips/{id}/documents`, `POST /api/trips/{id}/documents/metadata`
- `GET /api/currency/rate`, `GET /api/currency/convert`
- `POST /api/ai/parse-intent`

## Что осталось / TODO

- В dev есть insecure fallback по `X-Telegram-User-Id`. Для prod выставь `DEV_ALLOW_INSECURE_AUTH=0` и проверь, что Mini App работает только из Telegram.
- Ручные доли (manual shares) — архитектура заложена, UI пока только равнодолевое деление.
- Settlement workflow «отметить как погашено» — модель есть, кнопок в UI нет.
- Mini App upload документов — TODO. В MVP upload через бота.
- Webhook режим бота — оставлен endpoint, но в polling-режиме всё работает.
- При старте API таблицы создаются через `Base.metadata.create_all`. В prod — Alembic.

## Acceptance checklist

- [x] Запускается локально (uvicorn + run_bot.py + vite).
- [x] Можно создать поездку (Mini App / `/newtrip`).
- [x] Можно добавить участников (`/join` в группе).
- [x] Можно добавить расход в разной валюте.
- [x] Виден кто кому должен (`/balance`, страница Балансов).
- [x] Можно открыть Mini App.
- [x] Можно сохранить билет/бронь через Telegram document upload.
- [x] Можно найти документ командой `/docs`.
- [x] Можно конвертировать валюту.
- [x] Нет платных обязательных API.
- [x] Нет хранения паспортов/виз/ID.
- [x] Есть `.env.example` (backend и frontend).
- [x] Есть базовые unit-тесты (parser, balances, currency, documents).
