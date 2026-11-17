# shared_web — общие формы сайтов

Формы, одинаковые на всех сайтах parlaments, — один код на все сайты (gosduma/web/sozd_web — схема `sozd`,
knesset/web/kns_web — схема `kns`, будущие сайты). Сайты отличаются только схемой БД и меткой журнала.

| Форма | Бэкенд | Страница SPA | Объекты БД (в схеме сайта) |
|---|---|---|---|
| Log (`/logs/`) | `logs.py` | `frontend/pages/LogsPage.tsx` | `v_logs` |
| Гости сайта (`/guests/`) | `guests.py` | `frontend/pages/GuestsPage.tsx` | `nsi_guests`, `his_guests_page`, `nsi_emails`, `his_emails_hist` (модель из четырёх таблиц, см. ниже) |
| Параметры сервисов (`/functions/`) | `functions.py` | `frontend/pages/FunctionsPage.tsx` | `nsi_parser_functions`, `v_nsi_functions_params`, объекты `parser_functions`, `functions_params` |

Учёт посетителей, по которому строится «Гости сайта», — тоже общий: `visits.py`. Модель данных — четыре таблицы схемы сайта
(объекты `emails` и `guests`): `nsi_emails` — пользователи (`sh_name` — email, `first_date`, `last_date`, `count` — входов),
`nsi_guests` — гости: пара «IP + пользователь» (`sh_name` — IP, `country`, `city`, `email`; пусто — аноним),
`his_guests_page` — история гостя: открытые страницы, `his_emails_hist` — история пользователя: каждый вход — строка
`LOGIN; IP=<ip>; country=<страна>; city=<город>`. IP клиента — первый адрес `X-Forwarded-For` (дальше — прокси), локальные
заходы (127.0.0.1) не учитываются, вход — `register_login(request, user_name)`, открытая страница — `register_page(name)`.
Сайты вызывают его из `login.py` и `common.write_log`. Таблицы в схеме создаёт кнопка **Guests** формы «Классы» в modeler_web
(классы и параметры записываются в метаданные, затем создаются реальные таблицы БД; на схеме с прежней моделью из двух таблиц
достраиваются только emails и guests.email). Перенос накопленных данных прежней модели (входы как «Login (<имя>)» в
`his_guests_page`) — `migrations/guests_two_to_four_tables.sql`.

Все три формы — только для администратора: сайт закрывает их на сервере (sozd-web — `admin_forms_only` в
`start_sozd_web.py`, kns-web — в `start_kns_web.py` по `api_v2.ADMIN_FORMS`).

## Бэкенд

Модуль формы импортирует модули **сайта, в котором запущен**: `config` и `common` (они лежат в папке сайта, а она —
рабочая папка и `sys.path[0]`). Подключение в сайте — модуль-обёртка, например `forms/guests/guests.py`:

```python
from shared_web.guests import prepare_form  # noqa: F401
```

Что нужно от сайта:

- `config.SCHEMA` — схема БД сайта; `config.LOG_SRC` — метка сайта в журнале (`sozd_web`, `kns_web`).
- `common`: сессия — `get`, `add`, `default`, `exist`; REST — `send_rest(mes, directive='GET', params=None, lang='',
  token_user=None)`; журнал — `write_log_db(level, src, msg, page=None, file_name='', law_id='', td=None)`,
  `write_log(source, request, law_id='', mes=...)`; формы — `init_form(request, endpoint)`,
  `default_form(array, answer, prefix)`, `save_form(array, answer, prefix)`, `define_param_for_page(request, answer)`,
  `define_pages(answer)`, `choose_language(request)`, `get_where(search, columns)`; даты — `get_date_sql(st, time_zone)`,
  `get_st_date`, `calc_day`, `st_today`, `get_duration`; `what_change(unit, current, keys=None)`;
  проверка ввода для SQL — `sql_date(value, default='')` (дата `YYYY-MM-DD`).
  В sozd-web и kns-web эти функции одинаковы (сессия в cookie, без `user_id`).

## Фронтенд

`frontend/` — страницы (`pages/`), общие компоненты (`components/`: `TableControls`, `SearchField`, `DayNavigator`,
`logTime`) и переводы (`locales.ts`: `EN_SHARED_WEB`, `HE_SHARED_WEB`).

- Модули сайта страницы берут через alias `@app/...` (`useForm`, `api`, `i18n`, `components/layout`, `LoadingBar`,
  `FlashMessages`, `SplitPane`), общие — через `@shared-web/...`.
- Подключение в сайте (`frontend/`): в `vite.config.ts` — `resolve.alias` `@app` → `./src`, `@shared-web` →
  `../../../../shared_web/frontend` и `resolve.dedupe` для npm-пакетов (у `shared/` нет своего `node_modules`, пакеты
  берутся из проекта сайта); в `tsconfig.app.json` — те же `paths` (плюс `"*"` → `node_modules/@types/*`,
  `node_modules/*`) и `include` папки `shared_web/frontend`. В сайте — реэкспорты: `src/pages/LogsPage.tsx` =
  `export { default } from '@shared-web/pages/LogsPage'`, так же компоненты в `src/components/`.
- Словарь сайта подмешивает `EN_SHARED_WEB` (и `HE_SHARED_WEB` для иврита) из `@shared-web/locales`.
- Docker: стадия сборки SPA повторяет структуру репозитория (`WORKDIR /repo/<путь сайта>/frontend`,
  `COPY shared_web/frontend/ /repo/shared_web/frontend/`), чтобы относительный путь alias совпадал.
- Изменения в `shared_web/**` запускают деплой только сайтов (фильтры путей их workflow); `shared_web` — отдельная папка, а не часть `shared/`, чтобы правка форм не передеплоивала остальные сервисы.
