import json
import datetime

from flask import flash

import config
import common
import cloud
from common import get, add

MAX_ROWS = 3000


def load_list_rss(answer):
    """Список новостных лент (для фильтра «Канал»)."""
    answer['list_rss'] = []
    url = 'v2/entity/values?app_code={schema}&object_code=rss_list&column_order=id desc'.format(schema=config.SCHEMA)
    ans, is_ok, status = common.send_rest(url, params={"columns": "id, sh_name, lang"})
    if not is_ok:
        flash(str(ans), 'warning')
        return
    answer['list_rss'] = sorted({r['sh_name'].strip() for r in json.loads(ans) if r.get('sh_name')})


def load_themes(answer):
    """Список тем поисковых образов (для фильтра «Тема»)."""
    answer['themes'] = []
    url = 'v2/entity/values?app_code={schema}&object_code=rss_themes'.format(schema=config.SCHEMA)
    ans, is_ok, status = common.send_rest(url)
    if not is_ok:
        flash(str(ans), 'warning')
        return
    answer['themes'] = sorted({r['sh_name'] for r in json.loads(ans) if r.get('sh_name')})


def load_day(year, month, day):
    """За сутки (локальное время пользователя) все новости сразу со всеми языковыми вариантами заголовка/описания -
    выбор языка отображения, поиск, фильтры и сортировка происходят в браузере, без повторного запроса к серверу.
    LEFT JOIN + агрегация тем: сообщения без темы не теряются, с несколькими темами - не задваиваются."""
    tz = get('time_zone') or 0
    date_begin = common.get_date_sql([year, month, day], tz)
    t = datetime.datetime(year, month, day) + datetime.timedelta(days=1)
    date_end = common.get_date_sql([t.year, t.month, t.day], tz)

    query = """
        select a.id, a.rss, a.name_rss, a.author, a.lang, a.url, a.file, a.error_translator,
               a.public_date, a.at_date_time,
               a.title_ru, a.title_en, a.title_he,
               a.description_ru, a.description_en, a.description_he,
               string_agg(distinct b.sh_name, ', ') as themes
        from {schema}.v_nsi_rss_history a
        left join {schema}.get_list_theme_for_history b on a.id=b.id
        where (public_date is not NULL and public_date>='{begin}' and public_date<'{end}'
               or at_date_time>='{begin}' and at_date_time<'{end}')
        group by a.id, a.rss, a.name_rss, a.author, a.lang, a.url, a.file, a.error_translator,
                 a.public_date, a.at_date_time, a.title_ru, a.title_en, a.title_he,
                 a.description_ru, a.description_en, a.description_he
        order by coalesce(a.at_date_time, a.public_date) desc
        limit {limit};
    """.format(schema=config.SCHEMA, begin=date_begin, end=date_end, limit=MAX_ROWS)
    ans, is_ok, status_code = common.send_rest('v2/execute', 'PUT', params={"script": query},
                                               token_user=get('token'))
    if not is_ok:
        flash('Ошибка получения новостей: ' + str(ans), 'warning')
        return []
    rows = json.loads(ans)
    for row in rows:
        for key in ('description_ru', 'description_en', 'description_he'):
            if row.get(key) and row[key].endswith('...'):
                row[key] = row[key][:-3]
        row['themes'] = row['themes'] or ''
    return rows


def find_date(news_id):
    """Дата новости (в часовом поясе пользователя, как и load_day) по её id; None — новости нет."""
    query = "select coalesce(at_date_time, public_date) as dt from {schema}.v_nsi_rss_history where id={id} limit 1;".format(
        schema=config.SCHEMA, id=int(news_id))
    ans, is_ok, status_code = common.send_rest('v2/execute', 'PUT', params={"script": query},
                                               token_user=get('token'))
    if not is_ok:
        flash('Ошибка поиска новости: ' + str(ans), 'warning')
        return None
    rows = json.loads(ans)
    if not rows or not rows[0].get('dt'):
        return None
    return common.convert_time_to_timezone(rows[0]['dt'].replace('T', ' '), get('time_zone') or 0, format='%Y-%m-%d')


def prepare_form(request):
    """Лента новостей за сутки. POST-поля: st_date (сутки, YYYY-MM-DD), find_id (перейти к новости по ID: сутки этой
    новости, par['select_id']), delete_id (удалить новость — только администратор)."""
    answer = dict()
    st = common.init_form(request, '/news_board/')
    if st:
        answer['redirect'] = st
        return answer
    common.default('news_board_st_date', common.local_today())
    st_date = get('news_board_st_date')
    answer['select_id'] = None
    if request.method == 'POST':
        common.choose_language(request)
        st_date = common.sql_date(request.form.get('st_date'), st_date)
        find_id = common.sql_digits(request.form.get('find_id'))
        if find_id:
            found = find_date(find_id)
            if found:
                st_date = found
                answer['select_id'] = int(find_id)
            else:
                answer['not_found'] = int(find_id)
        delete_id = common.sql_digits(request.form.get('delete_id'))
        if delete_id:
            if common.is_admin():
                cloud.delete_new(delete_id, True)
            else:
                flash('Удалять новости может только администратор', 'warning')
    else:
        common.write_log('Новости (дашборд)', request)
    add('news_board_st_date', st_date)
    load_list_rss(answer)
    load_themes(answer)
    year, month, day = (int(x) for x in st_date.split('-'))
    answer['st_date'] = st_date
    answer['today'] = common.local_today()
    answer['data'] = load_day(year, month, day)
    answer['max_rows'] = MAX_ROWS
    return answer
