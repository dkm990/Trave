# Implementation Plan — Yo Travel Mini App

## Audit
Workspace `E:\Projects\Yo` пустой на старте. Архитектуру строим с нуля без тяжёлого наследия.

## Final architecture

```
Yo/
├── backend/                FastAPI + aiogram3 + SQLAlchemy2 + Alembic
│   ├── app/
│   │   ├── api/            REST endpoints для Mini App и webhook
│   │   ├── bot/            aiogram routers / handlers
│   │   ├── ai/             AIProvider interface + rule-based + ollama
│   │   ├── services/       TripService, ExpenseService, BalanceService,
│   │   │                   CurrencyService, DocumentService
│   │   ├── models/         SQLAlchemy ORM
│   │   ├── schemas/        Pydantic DTO
│   │   ├── auth/           Telegram initData validation
│   │   ├── config.py       pydantic-settings
│   │   ├── database.py     async engine + session
│   │   └── main.py         FastAPI app + lifespan
│   ├── alembic/            миграции (env поднимает модели через metadata)
│   ├── tests/              pytest unit tests
│   ├── run_bot.py          long polling entrypoint
│   ├── requirements.txt
│   └── .env.example
├── frontend/               React + Vite + TypeScript Mini App
│   ├── src/
│   │   ├── api/            fetch wrappers
│   │   ├── pages/          Trips, Dashboard, Converter, Expenses, Balances, Documents
│   │   ├── components/
│   │   ├── telegram/       window.Telegram.WebApp helpers
│   │   └── styles/
│   └── ...
├── docs/
│   └── implementation-plan.md
├── docker-compose.yml      опциональный Postgres
├── README.md
└── .gitignore
```

## Принципы

- SQLite по умолчанию, Postgres опционально через docker-compose.
- Все суммы храним как `Numeric(18, 4)` в копейках/центах? — Нет, держим Decimal с точностью 4. Округление при отображении.
- Все расходы внутри поездки нормализуем в `default_currency` через CurrencyService. Если курс недоступен и нет кеша — пишем расход как `pending_confirmed` и ставим `exchange_rate=null`, балансы пересчитываем когда курс появится. В MVP проще: при недоступности API — отказ с сообщением, плюс fallback на последний кеш не старше 7 дней.
- AI provider: интерфейс `AIProvider.parse_intent(text, context) -> Intent`. Default — `RuleBasedProvider`. Опционально `OllamaProvider` (HTTP /api/chat). Никогда не пишем расход без подтверждения.
- Бот в группах работает только на команды/reply/mention (`privacy mode = enabled` у BotFather + проверки в handlers).
- Документы: храним только `file_id` + metadata. Никаких загрузок на сервер. Тип `passport/visa/id` — отказ с предупреждением.
- Auth Mini App: `validate_init_data` через HMAC по бот токену. В MVP проверяется, но если фронт открыт вне Telegram — допускаем dev mode по флагу `DEV_ALLOW_INSECURE_AUTH=1`.

## Этапы (см. README для детальных команд)
1. Skeleton + config + DB models + Alembic init
2. Services (Trip, Expense, Balance, Currency, Document) + tests
3. Bot handlers (private + group) + confirmation flow
4. Mini App pages + Telegram theme
5. AI rule-based parser + Ollama optional
6. Polish + README

## Известные TODO MVP→next
- Ручные доли (manual shares) — архитектура заложена в `ExpenseShare.share_amount_base`, но UI/parser оставляем равнодолевое деление.
- Settlement workflow «отметить как погашено» — базовая запись есть, расширенный workflow позже.
- Mini App upload документов — TODO, основной upload через бота.
- Строгая validation initData всегда включена в prod, в dev возможен insecure mode.
- Webhook mode для бота: оставлен интерфейс, по умолчанию запускаем polling.
