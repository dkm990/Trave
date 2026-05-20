# Development and Staging Workflow

## Branches

- `main`: production-ready code only.
- `staging`: code deployed to staging for Telegram Mini App checks.
- `feature/*`, `fix/*`, `setup/*`: working branches opened as pull requests into `staging` first.

After staging verification, merge `staging` into `main` through a pull request and deploy production manually.

## Local Setup

Backend:

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate  # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest -q
```

Frontend:

```bash
cd frontend
npm ci
npm run dev
npm run build
```

Use local or staging test credentials only. Do not use the production bot token locally.

## Staging Environment Plan

Recommended domains:

- Mini App frontend: `staging.traveai.duckdns.org`
- API/backend: same origin under `/api` or `api-staging.traveai.duckdns.org`

Recommended staging environment variables:

Root `.env` for staging compose:

```env
MINI_APP_DOMAIN=staging.traveai.duckdns.org
VITE_API_BASE_URL=
DATABASE_URL=sqlite+aiosqlite:////app/data/yo-staging.db
DEV_ALLOW_INSECURE_AUTH=0
POSTGRES_USER=yo_staging
POSTGRES_DB=yo_staging
POSTGRES_PASSWORD=
```

Backend `.env` for staging:

```env
APP_ENV=staging
BOT_TOKEN=
TELEGRAM_BOT_TOKEN=
TELEGRAM_BOT_USERNAME=
WEBAPP_URL=https://staging.traveai.duckdns.org
MINI_APP_URL=https://staging.traveai.duckdns.org
DATABASE_URL=sqlite+aiosqlite:////app/data/yo-staging.db
DEV_ALLOW_INSECURE_AUTH=0
FLIGHT_PROVIDER=mock
AERODATABOX_API_KEY=
```

Frontend `.env` for staging:

```env
VITE_API_BASE_URL=
```

If frontend and API are split across domains, set `VITE_API_BASE_URL` to the staging API origin and configure backend `CORS_ORIGINS` accordingly.

## Telegram Staging Bot

Create a separate bot in BotFather for staging:

1. `/newbot` for a staging-only bot.
2. Configure Mini App URL to `https://staging.traveai.duckdns.org`.
3. Use the staging token only in staging `backend/.env`.
4. Do not reuse production token or production Mini App menu button.

## Pre-PR Checklist

- `git status --short --branch` is clean except intended files.
- No `.env`, tokens, keys, database files, dumps, or build artifacts are staged.
- Backend checks run or their failure is documented.
- Frontend build runs or its failure is documented.
- Staging deployment and Telegram Mini App smoke test are completed before production.
