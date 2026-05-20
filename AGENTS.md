# AGENTS.md

## Production Safety

- Do not touch the production VPS, production database, Caddy config, Telegram webhook, or production bot token unless the user explicitly asks for that exact production action.
- Do not deploy automatically from routine development tasks.
- Treat `main` as production. Make changes on a separate branch and prepare a pull request.
- Test changes on staging before production deployment.

## Secrets

- Never commit `.env`, API keys, Telegram bot tokens, database dumps, private keys, or generated credentials.
- Do not use the production Telegram bot token for local or staging tests.
- Use a separate staging Telegram bot token and separate staging Mini App URL.
- If a command prints secrets, stop and redact the output before reporting.

## Development Workflow

- Start each task by checking `git status --short --branch`.
- Keep changes scoped to the requested task.
- Use separate branches, for example `feature/...`, `fix/...`, or `setup/...`.
- Before finishing, run available checks:
  - backend: `pytest -q` from `backend/`
  - frontend: `npm run build` from `frontend/`
  - compose validation when Docker is available: `docker compose config --quiet`
- If a check fails or cannot run, report the exact command and reason. Do not hide failures.

## Environment Policy

- Local development uses local `.env` files copied from examples.
- Staging must use separate domains, separate database/storage, and a staging bot token.
- Production environment files are managed manually on the VPS and are not part of source control.
