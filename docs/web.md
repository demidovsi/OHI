# OHI — веб-приложение (`web/`)

Сайт мониторинга СМИ: лента собранных новостей, карточка новости (правка, перевод), аналитика, новостные ленты
(RSS), темы — поисковые образы, лог чата и служебные формы администратора. Часть монорепозитория OHI (рядом —
`server/`, фоновый сборщик новостей, и `shared/` — код, общий для web и server).

С версии 2.0.0 (20.10.2026) сайт устроен так же, как сайты репозитория `parlaments` (sozd-web, kns-web):
Flask отдаёт JSON API, интерфейс — SPA (React + MUI). Классический интерфейс (Jinja-шаблоны, jQuery, Bootstrap,
`users_session.py`, `language.py`) удалён. Языки интерфейса — русский, английский, иврит (иврит — справа налево).

Точка входа — `web/main_ohi_web.py`. Деплой — Google Cloud Run (`web/Dockerfile`, `.github/workflows/deploy-web.yml`): сервис
`ohi-web` (europe-central2, https://ohi-web-16542874441.europe-central2.run.app; до 21.10.2026 — `llm-web`), секреты
Secret Manager `ohi-web-url`, `ohi-web-kirill`, `ohi-web-flask-secret`. Сервис `llm-web` только перенаправляет на `ohi-web`
(`tools/llm_web_redirect`) — для ранее отправленных ссылок чат-бота. Адрес сайта для ссылок чат-бота — параметр
`url` функции `web` («Параметры сервисов»).

## Архитектура

- **Данные сайт не хранит** — все запросы к БД идут через REST API бэкенда (`common.send_rest`, токен superadmin
  из `common.login_admin`, кэшируется на час).
- **Сессия — подписанная cookie Flask** (`ohi_session`, ключ `FLASK_SECRET_KEY`): в cookie — ключ сессии и
  «паспорт» пользователя (имя, права, тема, язык, часовой пояс), состояние форм (фильтры, страницы) — в памяти
  процесса (`common._STATE`). Перезапуск или другой экземпляр Cloud Run: пользователь остаётся залогинен, фильтры —
  по умолчанию. `user_id` в адресах больше нет; старые адреса `/<форма>/<user_id>/` перенаправляются на `/<форма>/`.
- **Часовой пояс пользователя** (`time_zone` сессии) — смещение от UTC **в часах** (как в parlaments; раньше — в
  минутах).
- **API** (`api_v2.py`): `POST /api/v2/login`, `GET /api/v2/me`, `POST /api/v2/logout`, `POST /api/v2/set_theme`,
  `GET|POST /api/v2/form/<форма>/` → `{par, upr, messages, redirect}`. Каждая форма — функция
  `prepare_form(request)` своего модуля; SPA шлёт form-encoded поля с теми же именами, что были у HTML-форм.
- **Права**: формы `logs`, `guests`, `functions` — только администратору (проверка на сервере,
  `main_ohi_web.admin_forms_only`); изменения в `new`, `rss`, `search_words` (управление) и удаление новостей —
  тоже только администратору (проверка в модулях форм), меню лишь прячет кнопки.
- **SPA** — `web/frontend` (Vite, React, MUI 9, react-chartjs-2), собирается в `frontend/dist`, отдаётся Flask'ом по
  всем адресам, кроме `/api/` и `/static/`. Каркас (тема, меню, сплиттеры, RTL, правила оформления) — из kns-web,
  конвенции — `web/frontend/PORTING.md`. Переводы — `frontend/src/locales/*.ts` (ключ — русская строка).
- **Общие формы** Log, Гости сайта, Параметры сервисов — **копия** `parlaments/shared_web` в `web/shared_web`
  (бэкенд `logs.py`, `guests.py`, `functions.py`, учёт посетителей `visits.py`; страницы `frontend/pages`).
  Файлы не правились — при обновлении в parlaments их можно скопировать заново. Единственная замена —
  `web/shared/secret_params.py`: сервисы OHI читают параметры функций открытым текстом, поэтому шифрования
  секретных параметров (`enc2:`) в OHI нет.
- **Форма входа**: внизу — сайт, версия, устройство, страна и город (по IP, `GET /api/v2/info?lang=`), текущее
  время с часовым поясом (как в sozd-web).
- **Вход из чат-бота** `/one_new/<id>/` — вход пользователем `llm` (`common.user_from_chat`, часовой пояс — по IP),
  затем лента новостей с открытой новостью (`/news_board/?open_id=<id>`).

## Страницы

| Меню | Форма | Бэкенд | Страница SPA |
|---|---|---|---|
| Новости / Лента новостей | `news_board` | `news_board.py` | `NewsBoardPage.tsx` |
| (карточка новости, диалог) | `new` | `new.py` | `components/NewsDialog.tsx` |
| Новости / Аналитика | `analyses` | `analyses.py` | `AnalysesPage.tsx` |
| Сайт / Новостные ленты | `rss` | `rss.py` | `RssPage.tsx` |
| Сайт / Поисковые образы | `search_words` | `search_words.py` | `SearchWordsPage.tsx` |
| Сайт / Лог чата | `chat_logs` | `chat_logs.py` | `ChatLogsPage.tsx` |
| Сайт / Log (adm) | `logs` | `shared_web/logs.py` | `shared_web/frontend/pages/LogsPage.tsx` |
| Сайт / Гости сайта (adm) | `guests` | `shared_web/guests.py` | `shared_web/frontend/pages/GuestsPage.tsx` |
| Сайт / Параметры сервисов (adm) | `functions` | `shared_web/functions.py` | `shared_web/frontend/pages/FunctionsPage.tsx` |

- **Лента новостей**: сервер отдаёт все новости суток (до 3000) со всеми языковыми вариантами; поиск, фильтры по
  каналу и теме, язык отображения, сортировка и пагинация — в браузере. Поля формы: `st_date`, `find_id` (перейти к
  новости по ID — сутки новости), `delete_id` (удаление — администратор). Выбранная новость запоминается и
  подсвечивается. Пустая дата («Все даты») — все новости, самые свежие 3000: тогда фильтры канала, темы и поиск
  (`channel`, `theme`, `search`) применяются уже в БД, и их смена перезапрашивает данные.
  Дата, канал и темы в строках таблицы — кнопки: нажатие задаёт фильтр (сутки этой новости, канал, тему).
- **Карточка новости** (`new`): `new_id`, `open` (открытие — читать из БД), `select_lang`, `title`, `description`,
  `full`; действия `save`, `refresh`, `translate_ru/en/he` (ChatGPT), `need_article` (перечитать статью с сайта,
  `article_parser.py`), `load_file`. Полный текст статьи — в Google Cloud Storage (`cloud.py`, бакет `llm_news`).
- **Аналитика**: сервер считает ряды (`par.chart`: labels, datasets, режим bar/line), график рисует SPA (прежде —
  HTML plotly с сервера).
- **Поисковые образы**: режимы `detail` (новости темы и текст с подсветкой образов), `diagram`, `service`
  (правка темы и её история — администратор). Удаление (темы, новости из темы, ленты) подтверждается диалогом SPA
  (прежней страницы `delete_unit` нет).

## Локальный запуск

```
cd web
python main_ohi_web.py        # http://127.0.0.1:8082, перед стартом пересобирает frontend/dist, если он устарел
```

Нужны `web/.env` (`URL`, `KIRILL`, `FLASK_SECRET_KEY` — см. `.env.example`) и Node 20.19+ для сборки SPA.
Разработка интерфейса: `cd web/frontend && npm run dev` (http://localhost:5175, API проксируется на :8082;
сайт тогда запускать с `SPA_BUILD=0`).

## Логирование

Журнал — таблица `ohi.logs` (`common.write_log_db`; форма «Log»): вход (`LOGIN`), открытие страниц (`USER`),
действия в карточке новости, ChatGPT, изменения лент/тем/параметров, ошибки API (`ERROR-500`), старт процесса
(`START WEB`). Посещения — история гостя (`nsi_guests`, `his_guests_page`, `shared_web/visits.py`).
