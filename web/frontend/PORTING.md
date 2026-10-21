# Страницы SPA — конвенции

Интерфейс сайта OHI — только этот SPA (классический Jinja/jQuery UI удалён 2026-10-20, версия 2.0.0).
SPA отдаётся из корня сайта, сессия — в cookie (`ohi_session`), `user_id` в адресах нет.
Каждая форма = одна React-страница в `src/pages/<Page>Page.tsx`.
Скелет (theme.ts, api.ts, useForm.ts, auth, AppShell, SplitPane...) скопирован из parlaments/knesset/web/kns_web/frontend;
theme.ts — без изменений, чтобы вид совпадал с сайтами parlaments. Общие страницы Log / Гости / Параметры сервисов —
копия parlaments/shared_web в web/shared_web (alias `@shared-web`).

## Как работает форма

1. `useForm(page)` (`src/useForm.ts`) — первая загрузка GET
   `/api/v2/form/<page>/`, ответ `{par, upr, messages, redirect}`.
   `par` — словарь, который возвращает `prepare_form(request)` модуля формы.
2. Любое действие пользователя → `submit(fields)` → POST с form-encoded полями.
   **Имена полей и кнопок — те, что разбирает бэкенд** (`<name>.py: prepare_form / define_param_form` и
   `common.define_param_for_page`; шаблоны классического UI — в истории git). Кнопка `left`
   → поле `{ left: 1 }`. Кнопка с id в имени `show<id>` → `{ ['show' + id]: 1 }`.
3. **В POST всегда отправляем полный набор полей формы** (как FormData старой
   формы): селекты, инпуты, скрытые поля, `row_count/page/search/sort/scroll`.
   Пустой POST ломает бэкенд (`int(None)`). Хелпер `baseFields(par)` в
   `components/TableControls.tsx` даёт базу; страница добавляет свои поля.
4. `redirect` в ответе — путь (`/login/` — не вошёл); `useForm` сам делает `navigate`.
   Роуты SPA — `/<page>/` (у форм нет аргументов пути). Прежние адреса `/ui/...` SPA снимает сама
   (`main.tsx`), адреса с `user_id` сервер перенаправляет без него.
5. Скачивание файлов (документы из GCS, `par.download_blob`) — `downloadFile('<page>', fields)` из
   `src/api.ts`: скрытый POST формы на `/api/v2/form/<page>/`, ответ — файл (`send_file`).
6. Flash-сообщения → `<FlashMessages messages onDismiss>`.
7. Таблицы с пагинацией/поиском/сортировкой → `<TableToolbar par onSubmit base>` и
   `<TablePagination par onSubmit base>`. `base` — поля формы, которые надо
   слать вместе с любым действием тулбара.

## UI-правила

- Только MUI (`@mui/material`, `@mui/icons-material`). Импорты по одному компоненту:
  `import Button from '@mui/material/Button'`.
- MUI 9: system-props (`fontWeight`, `display`, `mb`) на Typography/Link/Box НЕ
  работают как пропсы — только через `sx={{...}}`.
- Плотный, «аналитический» вид: `size="small"`, `Table size="small"`,
  `Paper variant="outlined"` для панелей фильтров. Не изобретать свою палитру:
  цвета — `color="primary|secondary|error|text.secondary"`.
- Семантика цветов старого UI: blue → ссылки/primary, green → secondary,
  red → error/акцент, выделенная строка → `<TableRow selected>`.
- Таблицы: `TableContainer component={Paper} variant="outlined"`, `stickyHeader`.
  Пустая таблица → строка «Нет данных».
- Графики (Chart.js в старом UI) → `react-chartjs-2` (`Bar`, `Pie`, `Line`);
  регистрируй нужные элементы через `Chart.register(...)` в файле страницы.
- Модалки старого UI → `Dialog`.
- Ссылки на внешние сайты (main.knesset.gov.il и т.п.) — `Link target="_blank" rel="noopener"`.
- Тексты, подсказки (`title`), подписи — переносим из старого шаблона на русском.
- Никаких `any` кроме `Par`. Типизируй строки таблицы интерфейсом.
- i18n: все тексты через `t('русская строка')`; переводы страницы — в своих файлах
  `src/locales/en.<group>.ts` (`EN_<GROUP>`) и `src/locales/he.<group>.ts` (`HE_<GROUP>`), они подхватываются
  автоматически (`import.meta.glob`). Языки: ru, en, he; строка без перевода показывается по-русски.

## Правила оформления (как в sozd-web, `gosduma/web/sozd_web/frontend/PORTING.md`; источник — BTC-5m `docs/WEB.md`)

1. **Форма не прокручивается.** Поля с данными кончаются по высоте окна, прокручиваются только таблицы, тексты и
   диаграммы. Каркас (`AppShell`) высотой ровно в экран; на странице — константы `components/layout.ts`: корень —
   `<Box sx={PAGE_SX}>`, основная таблица — `<TableContainer ... sx={FILL_SX}>` (никаких `maxHeight: 'calc(100vh - …)'`),
   панель с текстом — `FILL_TEXT_PANEL` + `FILL_TEXT_FIELD`. Фильтры, тулбары и пагинация сохраняют свою высоту.
2. **Панели бок о бок / одна над другой — через сплиттер** `components/SplitPane.tsx` (`storageKey` — имя формы, размер
   запоминается в `localStorage` с префиксом `ohi_split_`; двойной щелчок — размер по умолчанию; на узком экране —
   столбиком). Ширина меню тоже меняется сплиттером (`ohi_split_menu`).
3. **Полосы прокрутки** — единый стиль 10px, задан в `theme.ts` (`MuiCssBaseline`); там же `color-scheme` для встроенных
   элементов браузера (календарь в полях дат) в цветах темы.
4. **Диаграммы прокручиваются отдельно, ось X закреплена** — `HorizontalBarChart` (`components/charts.tsx`).
5. **Полоса загрузки не сдвигает форму** — только `<LoadingBar loading={loading} />` (в диалоге — `inDialog`).
6. **Ссылки на другие сайты — в новой вкладке** (глобально, `App.tsx: useExternalLinksInNewTab`).
7. **Заголовок страницы — путь по меню** («Заседания / Комитеты»), в меню — «Свернуть всё» / «Развернуть всё»,
   раскрытые группы запоминаются (`ohi_menu_open`).
8. **Иврит — справа налево.** При языке `he` документ получает `dir="rtl"` (`i18n.tsx`), тема MUI — `direction: 'rtl'`,
   стили зеркалит Emotion-плагин `@mui/stylis-plugin-rtl` (`App.tsx`, кэш `muirtl`). Поэтому в разметке не задавать
   жёстко `left`/`right` для элементов, которые должны зеркалиться (отступы MUI `pl`/`pr`, `ml`/`mr` зеркалятся
   сами); перетаскивание в `SplitPane` и края меню учитывает `theme.direction`. Текст документов на иврите — как и
   раньше `direction: 'rtl'` в своей ячейке/поле.
9. **Нет `user_id`.** Сессия — cookie (`ohi_session`), адреса — `/<page>/`.

## Проверка

- `cd frontend && npx tsc -b` — без ошибок.
- `cd frontend && npm run build` — сборка в `frontend/dist` (Node 20.19+; со старым Node — первой стадией Dockerfile,
  см. `project_docs/README.md`).
- Данные формы — через API локального Flask (`start_ohi_web.py`, :8082) после входа (`POST /api/v2/login`):
  `GET /api/v2/form/<page>/`.
- Dev-сервер: `npm run dev` (http://localhost:5175, проксирует `/api` и `/static` на :8082, см. `vite.config.ts`).

## Регистрация страницы

Экспорт по умолчанию из `src/pages/<Name>Page.tsx`, регистрация — в
`src/pages/registry.ts` (`page` → компонент), пункт меню — в `src/menu.ts`.
