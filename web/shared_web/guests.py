"""Общая форма сайтов («Гости сайта», /guests/: посетители, страницы и пользователи — nsi_guests, his_guests_page) — один код для всех сайтов parlaments (sozd-web, kns-web, ...).

Сайт отличается только схемой БД и меткой журнала: модуль работает с модулями того сайта, в котором запущен —
`config` (SCHEMA, LOG_SRC) и `common` (сессия, REST, журнал, помощники форм), см. shared_web/README.md.
"""
import json
from flask import flash
import config
import common
from common import write_log, get

S = config.SCHEMA

CHART_COLORS = [
    '#4e73df', '#1cc88a', '#e74a3b', '#f6c23e', '#36b9cc',
    '#858796', '#fd7e14', '#6f42c1', '#20c9a6', '#e83e8c',
    '#17a2b8', '#28a745', '#dc3545', '#ffc107', '#6c757d',
    '#007bff', '#6610f2', '#e91e63', '#ff5722', '#795548',
]

array_default = [
    {'key': 'scroll',    'value': 0},
    {'key': 'view_mode', 'value': 'guests'},
    {'key': 'date_from', 'value': ''},
    {'key': 'date_to',   'value': ''},
    {'key': 'search',    'value': ''},
    {'key': 'row_count', 'value': 30},
    {'key': 'page',      'value': 1},
    {'key': 'order_col', 'value': ''},
    {'key': 'order_dir', 'value': ''},
]


# Сортировка таблицы по колонке (поля формы order_col / order_dir): колонка — только из этого списка, в SQL
# попадает её выражение. Для каждого режима — колонки таблицы и сортировка по умолчанию.
SORTS = {
    'guests': ({'sh_name': 'g.sh_name', 'country': 'g.country', 'city': 'g.city', 'visits': 'visits',
                'last_visit': 'last_visit'}, ('visits', 'desc'), 'g.id'),
    'users': ({'username': 'a.username', 'logins': 'a.logins', 'unique_ips': 'a.unique_ips', 'last_ip': 'lg.last_ip',
               'country': 'lg.country', 'last_login': 'a.last_login'}, ('logins', 'desc'), 'a.username'),
    'pages': ({'value': 'h.value', 'visits': 'visits', 'unique_guests': 'unique_guests', 'last_visit': 'last_visit'},
              ('visits', 'desc'), 'h.value'),
}


def _order_by(answer, mode):
    """ORDER BY выбранной колонки (или по умолчанию) + уникальный ключ — стабильный порядок между страницами."""
    columns, (default_col, default_dir), tie = SORTS[mode]
    col = answer.get('order_col') if answer.get('order_col') in columns else default_col
    direction = 'ASC' if (answer.get('order_dir') or default_dir) == 'asc' else 'DESC'
    answer['order_col'], answer['order_dir'] = col, direction.lower()
    return f'ORDER BY {columns[col]} {direction} NULLS LAST, {tie}'


def _q(sql):
    ans, ok, _ = common.send_rest(
        f'v2/execute?app_code={config.SCHEMA}', 'PUT',
        params={'script': sql},
        token_user=get('token')
    )
    if not ok:
        flash(str(ans), 'warning')
        return []
    return json.loads(ans)


def _esc(s):
    return (s or '').replace("'", "''")


def _date_parts(date_from, date_to, col):
    """Границы выбранных суток пользователя в UTC. his_guests_page.dt — UTC (сервер БД в Etc/UTC), а даты
    фильтра пользователь выбирает по своему времени: сдвиг — его часовой пояс (time_zone сессии, часы)."""
    tz = int(get('time_zone') or 0)
    parts = []
    if date_from:
        parts.append(f"{col} >= DATE '{date_from}' - INTERVAL '{tz} hours'")
    if date_to:
        parts.append(f"{col} < DATE '{date_to}' + 1 - INTERVAL '{tz} hours'")
    return parts


def _join_date(date_from, date_to, col='h.dt'):
    """Условие для ON-части JOIN (ограничивает строки his_guests_page по дате)."""
    parts = _date_parts(date_from, date_to, col)
    return (' AND ' + ' AND '.join(parts)) if parts else ''


def _where_date(date_from, date_to, col='h.dt'):
    """Условие для WHERE (когда JOIN не нужен, например для запросов только по his)."""
    parts = _date_parts(date_from, date_to, col)
    return (' AND ' + ' AND '.join(parts)) if parts else ''


# ── Guests view ───────────────────────────────────────────────────────────────

def load_guests_count(answer):
    date_from = answer.get('date_from', '')
    date_to   = answer.get('date_to',   '')
    search    = _esc(answer.get('search', '').strip())
    date_f    = _join_date(date_from, date_to)
    search_f  = (f"WHERE (g.sh_name ILIKE '%{search}%' OR g.country ILIKE '%{search}%'"
                 f" OR g.city ILIKE '%{search}%')") if search else ''
    rows = _q(f"""
        SELECT COUNT(*) FROM (
            SELECT g.id
            FROM {S}.nsi_guests g
            LEFT JOIN {S}.his_guests_page h ON h.guests_id = g.id {date_f}
            {search_f}
            GROUP BY g.id, g.sh_name, g.country, g.city
        ) sub
    """)
    return int(rows[0]['count']) if rows else 0


def load_guests(answer):
    date_from  = answer.get('date_from', '')
    date_to    = answer.get('date_to',   '')
    search     = _esc(answer.get('search', '').strip())
    date_f     = _join_date(date_from, date_to)
    search_f   = (f"WHERE (g.sh_name ILIKE '%{search}%' OR g.country ILIKE '%{search}%'"
                  f" OR g.city ILIKE '%{search}%')") if search else ''
    row_count  = int(answer['row_count'])
    offset     = row_count * (max(1, int(answer['page'])) - 1)
    return _q(f"""
        SELECT g.id, g.sh_name, g.country, g.city,
               COUNT(h.guests_id)  AS visits,
               MAX(h.dt)           AS last_visit
        FROM {S}.nsi_guests g
        LEFT JOIN {S}.his_guests_page h ON h.guests_id = g.id {date_f}
        {search_f}
        GROUP BY g.id, g.sh_name, g.country, g.city
        {_order_by(answer, 'guests')}
        LIMIT {row_count} OFFSET {offset}
    """)


def load_country_chart(date_from, date_to):
    date_f = _join_date(date_from, date_to)
    rows = _q(f"""
        SELECT COALESCE(NULLIF(g.country, ''), 'Не определено') AS country,
               COUNT(DISTINCT g.id) AS cnt
        FROM {S}.nsi_guests g
        LEFT JOIN {S}.his_guests_page h ON h.guests_id = g.id {date_f}
        GROUP BY country
        HAVING COUNT(h.guests_id) > 0 OR '{date_from}' = ''
        ORDER BY cnt DESC
        LIMIT 15
    """)
    if not rows:
        return '{}'
    labels = [r['country'] for r in rows]
    data   = [int(r['cnt']) for r in rows]
    return json.dumps({
        'type': 'multi', 'chart_type': 'pie',
        'labels': labels,
        'datasets': [{'label': 'Посетители', 'data': data,
                      'backgroundColor': CHART_COLORS[:len(labels)]}]
    }, ensure_ascii=False)


# ── Pages view ────────────────────────────────────────────────────────────────

def load_pages_count(answer):
    date_from = answer.get('date_from', '')
    date_to   = answer.get('date_to',   '')
    search    = _esc(answer.get('search', '').strip())
    date_f    = _where_date(date_from, date_to)
    search_f  = f"AND h.value ILIKE '%{search}%'" if search else ''
    rows = _q(f"""
        SELECT COUNT(DISTINCT h.value)
        FROM {S}.his_guests_page h
        WHERE 1=1 {date_f} {search_f}
    """)
    return int(rows[0]['count']) if rows else 0


def load_pages(answer):
    date_from = answer.get('date_from', '')
    date_to   = answer.get('date_to',   '')
    search    = _esc(answer.get('search', '').strip())
    date_f    = _where_date(date_from, date_to)
    search_f  = f"AND h.value ILIKE '%{search}%'" if search else ''
    row_count = int(answer['row_count'])
    offset    = row_count * (max(1, int(answer['page'])) - 1)
    return _q(f"""
        SELECT h.value,
               COUNT(*)               AS visits,
               COUNT(DISTINCT h.guests_id) AS unique_guests,
               MAX(h.dt)        AS last_visit
        FROM {S}.his_guests_page h
        WHERE 1=1 {date_f} {search_f}
        GROUP BY h.value
        {_order_by(answer, 'pages')}
        LIMIT {row_count} OFFSET {offset}
    """)


def load_pages_chart(date_from, date_to):
    date_f = _where_date(date_from, date_to)
    rows = _q(f"""
        SELECT h.value, COUNT(*) AS visits
        FROM {S}.his_guests_page h
        WHERE 1=1 {date_f}
        GROUP BY h.value
        ORDER BY visits DESC
        LIMIT 15
    """)
    if not rows:
        return '{}'
    labels = [r['value'] for r in rows]
    data   = [int(r['visits']) for r in rows]
    colors = CHART_COLORS[:len(labels)]
    return json.dumps({
        'type': 'multi', 'chart_type': 'bar',
        'labels': labels,
        'datasets': [{'label': 'Посещения', 'data': data,
                      'backgroundColor': colors,
                      'borderColor': colors,
                      'borderWidth': 1}]
    }, ensure_ascii=False)


# ── Users view ───────────────────────────────────────────────────────────────

def load_users_count(answer):
    date_from = answer.get('date_from', '')
    date_to   = answer.get('date_to',   '')
    search    = _esc(answer.get('search', '').strip())
    date_f    = _where_date(date_from, date_to)
    search_f  = f"AND SUBSTRING(h.value FROM 'Login \\((.+)\\)') ILIKE '%{search}%'" if search else ''
    rows = _q(f"""
        SELECT COUNT(DISTINCT SUBSTRING(h.value FROM 'Login \\((.+)\\)'))
        FROM {S}.his_guests_page h
        WHERE h.value LIKE 'Login (%' {date_f} {search_f}
    """)
    return int(rows[0]['count']) if rows else 0


def load_users(answer):
    date_from = answer.get('date_from', '')
    date_to   = answer.get('date_to',   '')
    search    = _esc(answer.get('search', '').strip())
    date_f    = _where_date(date_from, date_to)
    search_f  = f"AND username ILIKE '%{search}%'" if search else ''
    row_count = int(answer['row_count'])
    offset    = row_count * (max(1, int(answer['page'])) - 1)
    return _q(f"""
        WITH logins AS (
            SELECT SUBSTRING(h.value FROM 'Login \\((.+)\\)') AS username,
                   h.guests_id, h.dt
            FROM {S}.his_guests_page h
            WHERE h.value LIKE 'Login (%' {date_f}
        ),
        agg AS (
            SELECT username,
                   COUNT(*)               AS logins,
                   COUNT(DISTINCT guests_id) AS unique_ips,
                   MAX(dt)               AS last_login
            FROM logins
            WHERE username IS NOT NULL {search_f}
            GROUP BY username
        ),
        last_geo AS (
            SELECT DISTINCT ON (l.username)
                   l.username, g.country, g.city, g.sh_name AS last_ip
            FROM logins l
            JOIN {S}.nsi_guests g ON g.id = l.guests_id
            WHERE l.username IS NOT NULL
            ORDER BY l.username, l.dt DESC
        )
        SELECT a.username, a.logins, a.unique_ips, a.last_login,
               lg.country, lg.city, lg.last_ip
        FROM agg a
        LEFT JOIN last_geo lg ON lg.username = a.username
        {_order_by(answer, 'users')}
        LIMIT {row_count} OFFSET {offset}
    """)


def load_users_chart(date_from, date_to):
    date_f = _where_date(date_from, date_to)
    rows = _q(f"""
        SELECT SUBSTRING(h.value FROM 'Login \\((.+)\\)') AS username,
               COUNT(*) AS logins
        FROM {S}.his_guests_page h
        WHERE h.value LIKE 'Login (%' {date_f}
        GROUP BY username
        ORDER BY logins DESC
        LIMIT 15
    """)
    if not rows:
        return '{}'
    labels = [r['username'] for r in rows if r['username']]
    data   = [int(r['logins']) for r in rows if r['username']]
    colors = CHART_COLORS[:len(labels)]
    return json.dumps({
        'type': 'multi', 'chart_type': 'bar',
        'labels': labels,
        'datasets': [{'label': 'Входов', 'data': data,
                      'backgroundColor': colors,
                      'borderColor': colors,
                      'borderWidth': 1}]
    }, ensure_ascii=False)


# ── Summary ───────────────────────────────────────────────────────────────────

def load_summary(date_from, date_to):
    date_f = _where_date(date_from, date_to)
    rows = _q(f"""
        SELECT
            (SELECT COUNT(DISTINCT id)   FROM {S}.nsi_guests)        AS total_guests,
            (SELECT COUNT(*)             FROM {S}.his_guests_page h
             WHERE 1=1 {date_f})                                      AS total_visits,
            (SELECT COUNT(DISTINCT value) FROM {S}.his_guests_page h
             WHERE 1=1 {date_f})                                      AS total_pages,
            (SELECT COUNT(DISTINCT guests_id) FROM {S}.his_guests_page h
             WHERE 1=1 {date_f})                                      AS active_guests,
            (SELECT COUNT(DISTINCT SUBSTRING(h.value FROM 'Login \\((.+)\\)'))
             FROM {S}.his_guests_page h
             WHERE h.value LIKE 'Login (%' {date_f})                 AS total_users
    """)
    return rows[0] if rows else {}


# ── Main ──────────────────────────────────────────────────────────────────────

def prepare_form(request):
    answer = {}
    st = common.init_form(request, '/guests/')
    if st:
        answer['redirect'] = st
        return answer

    common.default_form(array_default, answer, 'guests_')

    if request.method == 'POST':
        common.choose_language(request)
        common.define_param_for_page(request, answer)
        new_mode = request.form.get('view_mode', answer.get('view_mode', 'guests'))
        if new_mode != answer.get('view_mode'):
            answer['page'] = 1
            answer['scroll'] = 0
            answer['order_col'] = answer['order_dir'] = ''  # у другой таблицы — свои колонки
        elif 'order_col' in request.form:
            new_order = (request.form.get('order_col', ''), request.form.get('order_dir', ''))
            if new_order != (answer.get('order_col'), answer.get('order_dir')):
                answer['page'] = 1  # другая сортировка — с первой страницы
            answer['order_col'] = request.form.get('order_col', '')
            answer['order_dir'] = request.form.get('order_dir', '')
        answer['view_mode'] = new_mode
        # даты фильтра — только YYYY-MM-DD (идут в SQL)
        answer['date_from'] = common.sql_date(request.form.get('date_from', answer.get('date_from', '')))
        answer['date_to']   = common.sql_date(request.form.get('date_to',   answer.get('date_to',   '')))
        answer['search']    = request.form.get('search',    answer.get('search',    ''))
    else:
        write_log('Гости сайта', request)

    date_from = answer.get('date_from', '')
    date_to   = answer.get('date_to',   '')
    mode      = answer.get('view_mode', 'guests')

    answer['summary'] = load_summary(date_from, date_to)

    if mode == 'guests':
        answer['count'] = load_guests_count(answer)
        common.define_pages(answer)
        answer['data']        = load_guests(answer)
        answer['chart_json']  = load_country_chart(date_from, date_to)
        answer['chart_title'] = 'Посетители по странам'
    elif mode == 'users':
        answer['count'] = load_users_count(answer)
        common.define_pages(answer)
        answer['data']        = load_users(answer)
        answer['chart_json']  = load_users_chart(date_from, date_to)
        answer['chart_title'] = 'Топ пользователей по числу входов'
    else:
        answer['count'] = load_pages_count(answer)
        common.define_pages(answer)
        answer['data']        = load_pages(answer)
        answer['chart_json']  = load_pages_chart(date_from, date_to)
        answer['chart_title'] = 'Топ страниц по посещаемости'

    answer['title'] = 'Статистика посетителей сайта'
    common.save_form(array_default, answer, 'guests_')
    return answer
