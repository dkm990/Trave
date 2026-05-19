# syntax=docker/dockerfile:1.6
# ============================================================================
# Yo Mini App — production build статики, отдаётся через nginx.
# Caddy перед контейнером терминирует TLS и проксирует на :80.
# ============================================================================

FROM node:20-alpine AS builder

WORKDIR /app

# VITE_API_BASE_URL пустой = фронт ходит на тот же origin (Caddy проксирует /api).
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY . .
RUN npm run build

# ----------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# SPA-friendly конфиг с history fallback и кешированием хешированных ассетов.
COPY --from=builder /app/dist /usr/share/nginx/html
RUN printf '%s\n' \
    'server {' \
    '    listen 80;' \
    '    server_name _;' \
    '    root /usr/share/nginx/html;' \
    '    index index.html;' \
    '    # SPA fallback' \
    '    location / { try_files $uri $uri/ /index.html; }' \
    '    # Хешированные ассеты — длинный кеш' \
    '    location /assets/ {' \
    '        access_log off;' \
    '        add_header Cache-Control "public, max-age=31536000, immutable";' \
    '    }' \
    '    # index.html — без кеша' \
    '    location = /index.html {' \
    '        add_header Cache-Control "no-cache";' \
    '    }' \
    '}' > /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -qO- http://localhost/ >/dev/null 2>&1 || exit 1
