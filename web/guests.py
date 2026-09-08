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
]


def _q(user_id, sql):
    ans, ok, status = common.send_rest('v2/execute', 'PUT', params={"script": sql}, token_user=get(user_id, 'token'))
    if not ok:
        flash(str(ans), 'warning')
        return []
    return json.loads(ans)


def _esc(s):
    return (s or '').replace("'", "''")


def _join_date(date_from, date_to, col='h.dt'):
    """Условие для ON-части JOIN (ограничивает строки his_guests_page по дате)."""
    parts = []
    if date_from:
        parts.append(f"{col} >= '{_esc(date_from)}'")
    if date_to:
        parts.append(f"{col} <= '{_esc(date_to)} 23:59:59'")
    return (' AND ' + ' AND '.join(parts)) if parts else ''


def _where_date(date_from, date_to, col='h.dt'):
    """Условие для WHERE (когда JOIN не нужен, например для запросов только по his)."""
    parts = []
    if date_from:
        parts.append(f"{col} >= '{_esc(date_from)}'")
    if date_to:
        parts.append(f"{col} <= '{_esc(date_to)} 23:59:59'")
    return (' AND ' + ' AND '.join(parts)) if parts else ''


# ── Общие помощники для сокращения числа обращений к бэкенду ──────────────────
#
# Раньше загрузка формы делала отдельные REST-запросы (count, data) через
# v1/select и v1/content/count. Теперь: count "прицепляется" к data через
# оконную функцию COUNT(*) OVER(), а summary и chart объединяются в один запрос
# через UNION ALL (строки размечаются колонкой kind). Отдельный count-запрос
# остаётся как редкий fallback на случай, когда страница "перескочила" за
# пределы новой выборки (0 строк из-за OVER()).

def _build_chart_json(chart_type, labels, data, series_label):
    if not labels:
        return '{}'
    colors = CHART_COLORS[:len(labels)]
    dataset = {'label': series_label, 'data': data, 'backgroundColor': colors}
    if chart_type == 'bar':
        dataset['borderColor'] = colors
        dataset['borderWidth'] = 1
    return json.dumps({
        'type': 'multi', 'chart_type': chart_type,
        'labels': labels,
        'datasets': [dataset]
    }, ensure_ascii=False)


def _load_page_with_count(rows_fn, count_fn, user_id, answer):
    rows = rows_fn(user_id, answer)
    count = int(rows[0]['total_count']) if rows else None
    if count is None:
        count = count_fn(user_id, answer)
    answer['count'] = count
    common.define_pages(answer)
    if count and not rows:
        rows = rows_fn(user_id, answer)
    return rows


# ── Guests view ───────────────────────────────────────────────────────────────

def load_guests_count(user_id, answer):
    date_from = answer.get('date_from', '')
    date_to   = answer.get('date_to',   '')
    search    = _esc(answer.get('search', '').strip())
    date_f    = _join_date(date_from, date_to)
    having_f  = 'HAVING COUNT(h.guests_id) > 0' if (date_from or date_to) else ''
    search_f  = (f"WHERE (g.sh_name ILIKE '%{search}%' OR g.country ILIKE '%{search}%'"
                 f" OR g.city ILIKE '%{search}%')") if search else ''
    rows = _q(user_id, f"""
        SELECT COUNT(*) FROM (
            SELECT g.id
            FROM {S}.nsi_guests g
            LEFT JOIN {S}.his_guests_page h ON h.guests_id = g.id {date_f}
            {search_f}
            GROUP BY g.id, g.sh_name, g.country, g.city
            {having_f}
        ) sub
    """)
    return int(rows[0]['count']) if rows else 0


def load_guests_data(user_id, answer):
    date_from  = answer.get('date_from', '')
    date_to    = answer.get('date_to',   '')
    search     = _esc(answer.get('search', '').strip())
    date_f     = _join_date(date_from, date_to)
    having_f   = 'HAVING COUNT(h.guests_id) > 0' if (date_from or date_to) else ''
    search_f   = (f"WHERE (g.sh_name ILIKE '%{search}%' OR g.country ILIKE '%{search}%'"
                  f" OR g.city ILIKE '%{search}%')") if search else ''
    row_count  = int(answer['row_count'])
    offset     = row_count * (max(1, int(answer['page'])) - 1)
    return _q(user_id, f"""
        SELECT g.id, g.sh_name, g.country, g.city,
               COUNT(h.guests_id)  AS visits,
               MAX(h.dt)           AS last_visit,
               COUNT(*) OVER ()    AS total_count
        FROM {S}.nsi_guests g
        LEFT JOIN {S}.his_guests_page h ON h.guests_id = g.id {date_f}
        {search_f}
        GROUP BY g.id, g.sh_name, g.country, g.city
        {having_f}
        ORDER BY last_visit DESC NULLS LAST, g.id
        LIMIT {row_count} OFFSET {offset}
    """)


# ── Pages view ────────────────────────────────────────────────────────────────

def load_pages_count(user_id, answer):
    date_from = answer.get('date_from', '')
    date_to   = answer.get('date_to',   '')
    search    = _esc(answer.get('search', '').strip())
    date_f    = _where_date(date_from, date_to)
    search_f  = f"AND h.value ILIKE '%{search}%'" if search else ''
    rows = _q(user_id, f"""
        SELECT COUNT(DISTINCT h.value)
        FROM {S}.his_guests_page h
        WHERE 1=1 {date_f} {search_f}
    """)
    return int(rows[0]['count']) if rows else 0


def load_pages_data(user_id, answer):
    date_from = answer.get('date_from', '')
    date_to   = answer.get('date_to',   '')
    search    = _esc(answer.get('search', '').strip())
    date_f    = _where_date(date_from, date_to)
    search_f  = f"AND h.value ILIKE '%{search}%'" if search else ''
    row_count = int(answer['row_count'])
    offset    = row_count * (max(1, int(answer['page'])) - 1)
    return _q(user_id, f"""
        SELECT h.value,
               COUNT(*)                    AS visits,
               COUNT(DISTINCT h.guests_id) AS unique_guests,
               MAX(h.dt)                   AS last_visit,
               COUNT(*) OVER ()            AS total_count
        FROM {S}.his_guests_page h
        WHERE 1=1 {date_f} {search_f}
        GROUP BY h.value
        ORDER BY visits DESC
        LIMIT {row_count} OFFSET {offset}
    """)


# ── Summary + Chart (один запрос через UNION ALL) ──────────────────────────────

def load_summary_and_chart(user_id, date_from, date_to, mode):
    date_f = _where_date(date_from, date_to)
    if mode == 'guests':
        date_f_join = _join_date(date_from, date_to)
        chart_sql = f"""
            SELECT 'chart' AS kind, country AS label, cnt::text AS cnt FROM (
                SELECT COALESCE(NULLIF(g.country, ''), 'Не определено') AS country,
                       COUNT(DISTINCT g.id) AS cnt
                FROM {S}.nsi_guests g
                LEFT JOIN {S}.his_guests_page h ON h.guests_id = g.id {date_f_join}
                GROUP BY country
                HAVING COUNT(h.guests_id) > 0 OR '{_esc(date_from)}' = ''
                ORDER BY cnt DESC
                LIMIT 15
            ) t
        """
        chart_type, series_label, chart_title = 'pie', 'Посетители', 'Посетители по странам'
    else:
        chart_sql = f"""
            SELECT 'chart' AS kind, value AS label, cnt::text AS cnt FROM (
                SELECT h.value, COUNT(*) AS cnt
                FROM {S}.his_guests_page h
                WHERE 1=1 {date_f}
                GROUP BY h.value
                ORDER BY cnt DESC
                LIMIT 15
            ) t
        """
        chart_type, series_label, chart_title = 'bar', 'Посещения', 'Топ страниц по посещаемости'

    rows = _q(user_id, f"""
        SELECT 'summary' AS kind, 'total_guests' AS label,
               (SELECT COUNT(DISTINCT id) FROM {S}.nsi_guests)::text AS cnt
        UNION ALL
        SELECT 'summary', 'total_visits',
               (SELECT COUNT(*) FROM {S}.his_guests_page h WHERE 1=1 {date_f})::text
        UNION ALL
        SELECT 'summary', 'total_pages',
               (SELECT COUNT(DISTINCT value) FROM {S}.his_guests_page h WHERE 1=1 {date_f})::text
        UNION ALL
        SELECT 'summary', 'active_guests',
               (SELECT COUNT(DISTINCT guests_id) FROM {S}.his_guests_page h WHERE 1=1 {date_f})::text
        UNION ALL
        {chart_sql}
    """)

    summary, labels, data = {}, [], []
    for r in rows:
        if r['kind'] == 'summary':
            summary[r['label']] = int(r['cnt'])
        else:
            labels.append(r['label'])
            data.append(int(r['cnt']))

    return summary, _build_chart_json(chart_type, labels, data, series_label), chart_title


# ── Main ──────────────────────────────────────────────────────────────────────

def prepare_form(user_id, request):
    answer = {}
    st = common.init_form(user_id, request, '/guests/')
    if st:
        answer['redirect'] = st
        return answer

    common.default_form(user_id, array_default, answer, 'guests_')

    if request.method == 'POST':
        common.choose_language(user_id, request)
        common.define_param_for_page(request, answer)

        new_mode      = request.form.get('view_mode', answer.get('view_mode', 'guests'))
        new_date_from = request.form.get('date_from', answer.get('date_from', ''))
        new_date_to   = request.form.get('date_to',   answer.get('date_to',   ''))
        filters_changed = (new_mode != answer.get('view_mode') or
                            new_date_from != answer.get('date_from') or
                            new_date_to   != answer.get('date_to')   or
                            answer.get('change_search'))
        if filters_changed:
            answer['page'] = 1
            answer['scroll'] = 0
        answer['view_mode'] = new_mode
        answer['date_from'] = new_date_from
        answer['date_to']   = new_date_to
    else:
        write_log('Посетители', user_id, request)

    date_from = answer.get('date_from', '')
    date_to   = answer.get('date_to',   '')
    mode      = answer.get('view_mode', 'guests')

    if mode == 'guests':
        answer['data'] = _load_page_with_count(load_guests_data, load_guests_count, user_id, answer)
    else:
        answer['data'] = _load_page_with_count(load_pages_data, load_pages_count, user_id, answer)

    summary, chart_json, chart_title = load_summary_and_chart(user_id, date_from, date_to, mode)
    answer['summary']     = summary
    answer['chart_json']  = chart_json
    answer['chart_title'] = chart_title

    answer['title']    = 'Статистика посетителей сайта'
    answer['ajax_form'] = True
    common.save_form(user_id, array_default, answer, 'guests_')
    return answer
