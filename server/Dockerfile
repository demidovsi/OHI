# Собирается из корня монорепозитория: docker build -f server/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

# Базовые системные зависимости (нужны для сборки некоторых Python-пакетов)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Общий пакет ohi_shared (см. /shared)
COPY shared/ /shared/
RUN pip install --no-cache-dir /shared

# requirements.txt содержит "-e ../shared" (локальная разработка, уже установлен
# выше отдельно) и pywin32 (Windows-only) — обе строки не нужны в образе.
COPY server/requirements.txt .
RUN grep -vE '^(-e |pywin32)' requirements.txt > requirements_docker.txt \
    && pip install --no-cache-dir -r requirements_docker.txt \
    && rm requirements_docker.txt

# Устанавливаем Playwright + системные зависимости Chromium
RUN playwright install --with-deps chromium

# Копируем исходный код
COPY server/ .

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-u", "main_llm_server.py"]
