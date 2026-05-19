# syntax=docker/dockerfile:1.6
# ============================================================================
# Yo backend image — общий для FastAPI API и Telegram-бота.
# Multi-stage, non-root, slim, с healthcheck-friendly entrypoint.
# Один и тот же образ запускается двумя командами:
#   - uvicorn app.main:app --host 0.0.0.0 --port 8000   (API)
#   - python run_bot.py                                  (bot polling)
# ============================================================================

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Минимум build-зависимостей. Большинство колес есть как wheels.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

# Изолированный venv копируется как единое целое в runtime — никаких трюков с PYTHONPATH.
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

WORKDIR /build
COPY requirements.txt ./
RUN pip install --upgrade pip \
 && pip install -r requirements.txt

# ----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH=/opt/venv/bin:$PATH

# curl нужен для HEALTHCHECK; tini — корректный signal handling для PID 1.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl tini \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 1001 yo \
 && useradd --system --uid 1001 --gid yo --create-home yo

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# Каталог для SQLite и любых runtime-данных. Должен быть writable для non-root.
RUN mkdir -p /app/data && chown -R yo:yo /app

# Копируем код. Тесты, venv и БД отрезаются через .dockerignore.
COPY --chown=yo:yo . /app

USER yo

EXPOSE 8000

# Дефолт — API. Bot переопределяет command в docker-compose.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1
