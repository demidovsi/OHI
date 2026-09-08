# Собирается из корня монорепозитория: docker build -f web/Dockerfile .
FROM python:3.10-slim

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

COPY web/ .

EXPOSE 8080

CMD ["python", "main_ohi_web.py"]
