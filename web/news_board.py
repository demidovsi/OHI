import json
import datetime

from flask import flash

import config
import common
from common import get
from news import load_list_rss, load_themes, delete_new

MAX_ROWS = 3000


def load_day(user_id, year, month, day):
    """Отдаёт за сутки (локальное время пользователя, как в news.py) все
    новости сразу со всеми языковыми вариантами заголовка/описания - выбор
    языка отображения происходит мгновенно в браузере, без повторного
    запроса к серверу. LEFT JOIN + агрегация тем (в отличие от news.py,
    который через неявный INNER JOIN с get_list_theme_for_history и теряет
    сообщения без единой темы, и задваивает строки для сообщений с
    несколькими темами)."""
    # "or 0" - подстраховка на случай None (напр. пользователь вошёл в обход
    # обычной формы логина, где часовой пояс читается из браузера) - без неё
    # унарный минус над None валит страницу 500-й ошибкой.
    tz = get(user_id, 'time_zone') or 0
    date_begin = common.get_date_sql([year, month, day], -tz)
    t = datetime.datetime(year, month, day) + datetime.timedelta(days=1)
    date_end = common.get_date_sql([t.year, t.month, t.day], -tz)

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
                                               token_user=get(user_id, 'token'))
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


def prepare_form(user_id, request):
    """Первичная отдача страницы (GET) - справочники каналов/тем + данные за
    сегодня, чтобы первый показ обошёлся без лишнего похода за данными
    (дальше смена даты идёт через /api/news_board/<user_id>/data)."""
    answer = dict()
    st = common.init_form(user_id, request, '/news_board/')
    if st:
        answer['redirect'] = st
        return answer
    answer['list_rss'] = []
    answer['themes'] = []
    load_list_rss(answer)
    load_themes(answer)
    today = common.st_today()
    year, month, day = (int(x) for x in today.split('-'))
    answer['year'], answer['month'], answer['day'] = year, month, day
    answer['st_date'] = today
    answer['data'] = load_day(user_id, year, month, day)
    common.write_log('Новости (дашборд)', user_id, request)
    return answer
