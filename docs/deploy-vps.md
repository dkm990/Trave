# Деплой Yo на VPS

Step-by-step для переноса Telegram bot + Mini App на VPS через Docker compose.
TLS-сертификат выдаёт Caddy автоматически (Let's Encrypt).

## Что в стеке

- **api** — FastAPI (uvicorn), порт 8000 внутри сети.
- **bot** — тот же образ, команда `python run_bot.py` (long polling).
- **frontend** — nginx со статикой Mini App.
- **caddy** — reverse proxy + автоматический HTTPS, единственный с публичными портами 80/443.
- **postgres** *(опционально)* — через `docker-compose.postgres.yml`. По умолчанию SQLite в volume.

## 1. Требования на VPS

- Linux (Ubuntu 22.04+ / Debian 12 рекомендую).
- Открытые порты 80/443.
- Docker Engine 24+ и плагин `docker compose v2`.
- DNS-запись `A` (и `AAAA` если IPv6) на IP VPS до старта Caddy — иначе Let's Encrypt не выдаст сертификат.

Установка Docker одной строкой:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER  # перелогиниться
```

## 2. Клонирование и конфиг

```bash
git clone <repo-url> yo
cd yo

# Compose-уровень переменные
cp .env.example .env
nano .env      # MINI_APP_DOMAIN=yo.example.com и т.п.

# Секреты приложения
cp backend/.env.example backend/.env
nano backend/.env  # BOT_TOKEN, GEMINI_API_KEY, APP_TIMEZONE, MINI_APP_URL=https://yo.example.com
```

Обязательно проверить в `backend/.env`:

| Переменная | Prod-значение |
|------------|---------------|
| `DEV_ALLOW_INSECURE_AUTH` | `0` |
| `APP_ENV` | `prod` |
| `APP_TIMEZONE` | `Europe/Istanbul` (или ваша) |
| `BOT_TOKEN` | реальный токен |
| `MINI_APP_URL` | `https://yo.example.com` |
| `CORS_ORIGINS` | `https://yo.example.com` (не `*`) |
| `DATABASE_URL` | `sqlite+aiosqlite:////app/data/yo.db` (или Postgres URL) |

И в Telegram у `@BotFather`:

- `/setdomain` → `yo.example.com`
- `/setmenubutton` → `https://yo.example.com`

## 3. Запуск

### Вариант A — SQLite (по умолчанию)

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f api bot
```

Файл БД лежит в named-volume `yo_data` и виден контейнерам по пути `/app/data/yo.db`.

### Вариант B — Postgres

В `.env`:

```env
DATABASE_URL=postgresql+asyncpg://yo:<strong-password>@postgres:5432/yo
POSTGRES_PASSWORD=<strong-password>
```

Запуск с override:

```bash
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d --build
```

Перенос данных из существующего SQLite в Postgres — отдельная задача (использовать `pgloader` или ручной dump через скрипт). Для свежего инстанса просто запустить и дать `init_db` создать таблицы.

## 4. Проверка после старта

```bash
# Health
curl -fsS https://yo.example.com/health

# API через Caddy
curl -fsS https://yo.example.com/api/trips -H "X-Telegram-User-Id: 1"   # должен 401 в prod (insecure auth выключен)

# Бот
docker compose logs --tail=50 bot   # должно быть "Bot @<username> started in polling mode"
```

Открыть Mini App из Telegram — DOM должен подняться, `/api/trips` идёт через тот же origin.

## 5. Backup SQLite

Один раз настроить cron на хосте (БД всё равно в named-volume Docker):

```bash
sudo tee /etc/cron.daily/yo-backup >/dev/null <<'EOF'
#!/bin/sh
set -eu
TS=$(date +%Y%m%d-%H%M%S)
DEST=/var/backups/yo
mkdir -p "$DEST"
docker run --rm -v yo_yo_data:/data alpine \
    sh -c "cp /data/yo.db /data/yo.db.bak.$TS"
docker run --rm -v yo_yo_data:/data -v "$DEST":/out alpine \
    sh -c "cp /data/yo.db.bak.$TS /out/ && rm /data/yo.db.bak.$TS"
find "$DEST" -name 'yo.db.bak.*' -mtime +30 -delete
EOF
sudo chmod +x /etc/cron.daily/yo-backup
```

Перед деструктивными апдейтами (миграции, релиз) — снять снапшот вручную:

```bash
docker compose exec api sh -c 'cp /app/data/yo.db /app/data/yo.backup-$(date +%Y%m%d-%H%M%S).db'
```

## 6. Обновление

```bash
git pull
docker compose build
docker compose up -d
docker compose logs --tail=100 api bot
```

`api` стартует первым, `bot` ждёт его healthcheck. Idempotent миграции в `init_db` догонят SQLite-схему автоматически. Для Postgres лучше переключиться на Alembic — `alembic upgrade head` выполнить через `docker compose run --rm api alembic upgrade head`.

## 7. Polling vs Webhook

По умолчанию бот в long polling — проще, не требует публичного endpoint для Telegram. Этот режим работает за NAT и не зависит от cert lifecycle.

Если хотите webhook:

1. В `backend/.env` добавить `TELEGRAM_WEBHOOK_URL=https://yo.example.com/telegram/webhook`.
2. Реализовать endpoint в `app/api/webhook.py` (заглушка уже есть).
3. Отключить сервис `bot` в compose или поменять `command` на no-op.
4. Установить webhook: `curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://yo.example.com/telegram/webhook"`.

Для MVP polling достаточно.

## 8. Troubleshooting

| Симптом | Что проверить |
|---------|---------------|
| Caddy не выдаёт сертификат | DNS A-запись смотрит на VPS, порт 80 открыт, `MINI_APP_DOMAIN` в `.env` совпадает с записью |
| `bot` рестартится | `docker compose logs bot` — обычно неверный `BOT_TOKEN` или конфликт polling (запущена ещё одна копия с тем же токеном) |
| Mini App открывается, но 401 на API | `DEV_ALLOW_INSECURE_AUTH=0` корректно, но Mini App запускается не из Telegram (нет initData). Запустить из настоящего Telegram-клиента |
| `/api/*` возвращает 502 | Caddy не достучался до `api:8000` — `docker compose logs api`, проверить healthcheck |
| Конвертация валют падает | Frankfurter/ExchangeRate-Open сейчас даун. Бот ловит и идёт в кеш. Если кеш холодный — прогреть через `/rate USD RUB` |

## 9. Безопасность

- `backend/.env` — `chmod 600`, владелец non-root.
- Никогда не коммитить `.env` (защищено `.gitignore`).
- На VPS отключить root SSH login, поставить `ufw allow 22,80,443`.
- Регулярно `docker compose pull` для базовых образов (caddy, nginx, postgres) — обновления безопасности.
- Если хранится Postgres — backup с шифрованием через age/gpg перед выгрузкой во внешний storage.

## 10. Откат релиза

```bash
git checkout <previous-tag>
docker compose up -d --build
```

Если БД мигрировала несовместимо — восстановить из последнего бэкапа:

```bash
docker compose stop api bot
docker run --rm -v yo_yo_data:/data -v /var/backups/yo:/in alpine \
    sh -c "cp /in/yo.db.bak.<TIMESTAMP> /data/yo.db"
docker compose start api bot
```
