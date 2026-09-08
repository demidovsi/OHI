# OHI

Монорепозиторий для двух независимо деплоящихся сервисов мониторинга СМИ:

- **`web/`** — веб-интерфейс (Flask), бывший [LLM-web](https://github.com/demidovsi/LLM-web)
- **`server/`** — фоновый сборщик/обработчик новостей, бывший [LLM-server](https://github.com/demidovsi/LLM-server)
- **`shared/`** — пакет `ohi_shared` с кодом, который был байт-в-байт одинаковым в обоих проектах
  (`decode`/`encode`, `str1000`, `get_duration`). Вся остальная логика (REST-клиент, логирование,
  работа с облаком и т.д.) в `web` и `server` разошлась и по-прежнему живёт раздельно в каждом сервисе.

История коммитов исходных репозиториев в этот монорепозиторий не переносилась — она осталась
доступна в LLM-web и LLM-server на GitHub.

## Локальная разработка

Для каждого сервиса — своё окружение, `shared` ставится в него editable-пакетом:

```bash
cd web    # или server
python -m venv .venv
.venv/Scripts/activate           # Windows
pip install -r requirements.txt  # requirements.txt уже содержит "-e ../shared"
cp .env.example .env             # заполнить секреты
```

## Деплой

Сервисы деплоятся раздельно через два GitHub Actions workflow:

- `.github/workflows/deploy-web.yml` — триггерится на изменения в `web/**` или `shared/**`,
  собирает `web/Dockerfile` и деплоит на Cloud Run.
- `.github/workflows/deploy-server.yml` — триггерится на изменения в `server/**` или `shared/**`,
  собирает `server/Dockerfile`, пушит в ghcr.io и деплоит на прод-сервер по SSH.

Оба Dockerfile рассчитаны на сборку **из корня репозитория** (нужен доступ к `shared/`):

```bash
docker build -f web/Dockerfile -t llm-web .
docker build -f server/Dockerfile -t llm-server .
```
