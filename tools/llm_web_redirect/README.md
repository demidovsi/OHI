# llm-web → ohi-web

Сервис Cloud Run `llm-web` (прежнее имя сайта) после переименования в `ohi-web` (21.10.2026) только перенаправляет
(301) на https://ohi-web-16542874441.europe-central2.run.app с тем же путём и параметрами — для ссылок, уже
отправленных чат-ботом. Деплой вручную:

```
gcloud run deploy llm-web --source tools/llm_web_redirect --region europe-central2 --project playground-332710 \
    --allow-unauthenticated --clear-secrets --clear-env-vars
```
