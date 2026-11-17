"""Общая форма сайтов («Гости сайта», /guests/) — один код для всех сайтов; вид и данные — как у формы guests сайта GEO и формы
«Посетители схемы» modeler_web: дерево «дата → страна, город → IP → форма», плашки итогов, диаграмма и таблицы пользователей,
форм и мест.

Модель данных (схема сайта; объекты создаёт кнопка Guests формы classes в modeler_web): nsi_guests (IP, страна, город, пользователь email),
his_guests_page (открытые страницы гостя), nsi_emails (пользователи: входов, первый и последний вход), his_emails_hist (история
пользователя; входы — строки «LOGIN; IP=<ip>; country=<страна>; city=<город>»). Запись ведёт shared_web/visits.py.

Сайт отличается только схемой БД и меткой журнала: модуль работает с модулями того сайта, в котором запущен —
`config` (SCHEMA, LOG_SRC) и `common` (сессия, REST, журнал, помощники форм), см. shared_web/README.md.

Поля формы: ``mode`` — ``day`` (выбранные сутки по времени пользователя) или ``all`` (всё время), ``date`` — сутки
(YYYY-MM-DD, по умолчанию сегодня), ``search`` — поиск по стране, городу, IP, пользователю и форме (``&`` — И, ``;`` — ИЛИ).

Ответ формы: ``rows`` — обращения, сгруппированные по (дата, страна, город, IP, пользователь, форма) с числом ``n`` и временем
первого и последнего (UTC); ``users`` — пользователи за всё время (``has_users`` — есть ли в схеме пользователи сайта);
``total_guests`` — число гостей; ``mode``, ``date``, ``search``.
"""
import datetime
import json

from flask import flash

import common
import config
from common import get, write_log

S = config.SCHEMA

array_default = [
    {'key': 'scroll', 'value': 0},
    {'key': 'mode', 'value': 'day'},
    {'key': 'date', 'value': ''},
    {'key': 'search', 'value': ''},
]

MODES = ('day', 'all')
SEARCH_COLUMNS = ('b.country', 'b.city', 'b.sh_name', 'a.value')   # и e.sh_name (пользователь), если в схеме есть nsi_emails


def _esc(text):
    """Строка для SQL в одинарных кавычках без самих кавычек (и подстановочных знаков LIKE)."""
    return str(text).replace("'", "''").replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def _valid_date(text):
    """Дата YYYY-MM-DD или '' (если текст не дата): значение попадает в SQL."""
    try:
        return datetime.date.fromisoformat(str(text or '').strip()).isoformat()
    except ValueError:
        return ''


def _tz():
    """Часовой пояс пользователя (часы от UTC): время в таблицах хранится в UTC."""
    try:
        return int(get('time_zone') or 0)
    except (TypeError, ValueError):
        return 0


def _today_local():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=_tz())).date().isoformat()


def _day_range_utc(date):
    """Границы суток пользователя в UTC ('YYYY-MM-DD HH:MM:SS')."""
    begin = datetime.datetime.fromisoformat(date) - datetime.timedelta(hours=_tz())
    end = begin + datetime.timedelta(days=1)
    return begin.strftime('%Y-%m-%d %H:%M:%S'), end.strftime('%Y-%m-%d %H:%M:%S')


def _q(sql, quiet=False):
    """Запрос SELECT к схеме сайта: список строк (при ошибке — предупреждение формы, если не quiet, и None)."""
    ans, ok, _ = common.send_rest(f'v2/execute?need_answer=True&app_code={S}', 'PUT', params={'script': sql}, token_user=get('token'))
    if not ok:
        if not quiet:
            flash(str(ans), 'warning')
        return None
    try:
        data = json.loads(ans)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, list) else None


def has_users():
    """В схеме есть пользователи сайта: таблица nsi_emails и колонка email у гостей (иначе форма — только по гостям)."""
    rows = _q(f"SELECT (SELECT count(*) FROM information_schema.tables WHERE table_schema = '{S}' AND table_name = 'nsi_emails') AS t, "
              f"(SELECT count(*) FROM information_schema.columns WHERE table_schema = '{S}' AND table_name = 'nsi_guests' "
              f"AND column_name = 'email') AS c", quiet=True)
    return bool(rows) and int(rows[0]['t']) > 0 and int(rows[0]['c']) > 0


def search_cond(search, columns):
    """Условие поиска: ';' — ИЛИ между группами, '&' — И между словами группы; слово ищется без учёта регистра в любой из колонок."""
    groups = []
    for group in str(search or '').split(';'):
        words = [w.strip() for w in group.split('&') if w.strip()]
        if words:
            groups.append('(' + ' AND '.join(
                '(' + ' OR '.join(f"coalesce({col}, '') ILIKE '%{_esc(word)}%'" for col in columns) + ')' for word in words) + ')')
    return '(' + ' OR '.join(groups) + ')' if groups else ''


def visits_sql(mode, date, search, users):
    """Обращения гостей к страницам по (местная дата, страна, город, IP, пользователь, форма): число и время первого/последнего.
    users=False — в схеме нет пользователей сайта: колонка пользователя пустая."""
    # прежние записи «Login (<имя>)» в his_guests_page (до перехода на nsi_emails/his_emails_hist) - не страницы
    conds = ["a.value NOT LIKE 'Login (%'"]
    cond = search_cond(search, SEARCH_COLUMNS + (('e.sh_name',) if users else ()))
    if cond:
        conds.append(cond)
    if mode == 'day':
        begin, end = _day_range_utc(date)
        conds.append(f"a.dt >= '{begin}' AND a.dt < '{end}'")
    where = (' WHERE ' + ' AND '.join(conds)) if conds else ''
    user_expr = "coalesce(e.sh_name, '')" if users else "''"
    user_join = f' LEFT JOIN {S}.nsi_emails e ON e.id = b.email' if users else ''
    return (f"SELECT ((a.dt + interval '{_tz()} hours')::date)::text AS d, coalesce(b.country, '') AS country, "
            f"coalesce(b.city, '') AS city, b.sh_name AS ip, {user_expr} AS usr, coalesce(a.value, '') AS page, "
            f"count(*) AS n, min(a.dt)::text AS first_dt, max(a.dt)::text AS last_dt "
            f"FROM {S}.his_guests_page a JOIN {S}.nsi_guests b ON b.id = a.guests_id"
            f"{user_join}{where} GROUP BY 1, 2, 3, 4, 5, 6 ORDER BY 1 DESC, 2, 3, 4, 6")


def prepare_form(request):
    answer = {}
    st = common.init_form(request, '/guests/')
    if st:
        answer['redirect'] = st
        return answer

    common.default_form(array_default, answer, 'guests_')
    if request.method == 'POST':
        common.choose_language(request)
        mode = request.form.get('mode', answer['mode'])
        answer['mode'] = mode if mode in MODES else 'day'
        answer['date'] = _valid_date(request.form.get('date', answer['date']))
        answer['search'] = request.form.get('search', answer['search']).strip()[:100]
    else:
        write_log('Гости сайта', request)
    if not answer['date']:
        answer['date'] = _today_local()

    users_exist = has_users()
    answer.update({'rows': [], 'users': [], 'total_guests': 0, 'has_users': users_exist})
    rows = _q(visits_sql(answer['mode'], answer['date'], answer['search'], users_exist))
    answer['rows'] = rows or []
    if users_exist:
        answer['users'] = _q(f'SELECT id, sh_name, "count", first_date::text AS first_date, last_date::text AS last_date '
                             f'FROM {S}.nsi_emails ORDER BY "count" DESC NULLS LAST, id') or []
    total = _q(f'SELECT count(*) AS n FROM {S}.nsi_guests')
    answer['total_guests'] = int(total[0]['n']) if total else 0
    common.save_form(array_default, answer, 'guests_')
    return answer
