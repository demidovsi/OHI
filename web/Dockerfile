# Собирается из корня монорепозитория: docker build -f web/Dockerfile .

# --- Stage 1: сборка SPA (web/frontend -> web/frontend/dist) -------------------
# Структура папок — как в репозитории: SPA использует общие страницы web/shared_web/frontend
# (alias @shared-web, путь ../shared_web/frontend от папки frontend).
FROM node:22-alpine AS frontend
WORKDIR /repo/web/frontend
COPY web/frontend/package.json web/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/frontend/ ./
COPY web/shared_web/frontend/ /repo/web/shared_web/frontend/
RUN npm run build

# --- Stage 2: Python-приложение ------------------------------------------------
FROM python:3.11-slim

WORKDIR /app

# Общий пакет ohi_shared (см. /shared)
COPY shared/ /shared/
RUN pip install --no-cache-dir /shared

# requirements.txt содержит "-e ../shared" для локальной разработки — в образе
# shared уже установлен отдельно выше, поэтому эту строку не используем.
COPY web/requirements.txt .
RUN grep -v '^-e ' requirements.txt > requirements_docker.txt \
    && pip install --no-cache-dir -r requirements_docker.txt \
    && rm requirements_docker.txt

COPY web/*.py ./
COPY web/shared/ ./shared/
COPY web/shared_web/ ./shared_web/
COPY web/static/ ./static/

# Собранный SPA — интерфейс сайта, раздаётся Flask'ом по всем адресам (см. api_v2.py)
COPY --from=frontend /repo/web/frontend/dist ./frontend/dist

EXPOSE 8080

# exec-форма: gunicorn читает $PORT, заданный Cloud Run. Один процесс: состояние форм — в памяти (common.py)
CMD exec gunicorn --bind "0.0.0.0:${PORT:-8080}" --workers 1 --threads 8 --timeout 0 start_ohi_web:app
