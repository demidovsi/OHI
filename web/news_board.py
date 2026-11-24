import json
import datetime
import time

from flask import flash

import config
import common
import cloud
from common import get, add

MAX_ROWS = 3000
DESCRIPTION_LIMIT = 1000  # описание в таблице не длиннее (обрезанное заканчивается «…»); полный текст — в карточке новости


# Списки лент и тем почти не меняются (правятся в формах «Новостные ленты» и «Поисковые образы»): кэш в памяти процесса
# на минуту — без двух обращений к REST при каждом открытии/обновлении формы.
LIST_CACHE_TTL = 60
_list_cache = {}


def _cached(key, loader):
    """Значение loader() из кэша (не старше LIST_CACHE_TTL секунд); при ошибке загрузки (None) кэш не обновляется."""
    now = time.time()
    hit = _list_cache.get(key)
    if hit and now - hit[0] < LIST_CACHE_TTL:
        return hit[1]
    value = loader()
    if value is not None:
        _list_cache[key] = (now, value)
    return value


def _fetch_rss_names():
    url = 'v2/entity/values?app_code={schema}&object_code=rss_list&column_order=id desc'.format(schema=config.SCHEMA)
    ans, is_ok, status = common.send_rest(url, params={"columns": "id, sh_name, lang"})
    if not is_ok:
        flash(str(ans), 'warning')
        return None
    return sorted({r['sh_name'].strip() for r in json.loads(ans) if r.get('sh_name')})


def _fetch_theme_names():
    url = 'v2/entity/values?app_code={schema}&object_code=rss_themes'.format(schema=config.SCHEMA)
    ans, is_ok, status = common.send_rest(url)
    if not is_ok:
        flash(str(ans), 'warning')
        return None
    return sorted({r['sh_name'] for r in json.loads(ans) if r.get('sh_name')})


def load_list_rss(answer):
    """Список новостных лент (для фильтра «Канал»)."""
    answer['list_rss'] = _cached('rss', _fetch_rss_names) or []


def load_themes(answer):
    """Список тем поисковых образов (для фильтра «Тема»)."""
    answer['themes'] = _cached('themes', _fetch_theme_names) or []


def load_news(where):
    """Новости (не больше MAX_ROWS, самые свежие) сразу со всеми языковыми вариантами заголовка/описания - выбор
    языка отображения, поиск, фильтры и сортировка происходят в браузере, без повторного запроса к серверу.
    Темы собираются подзапросом только для отобранных строк (прежний LEFT JOIN с видом get_list_theme_for_history
    читал вид целиком — все связи и всю историю — ещё до отбора, это были ~80% времени запроса); сообщения без темы не
    теряются, с несколькими темами - не задваиваются. Фильтры (where) применяются к полным текстам в БД, а в ответ
    описания отдаются не длиннее DESCRIPTION_LIMIT (иначе ответ «Все даты»/поиска — мегабайты)."""
    def cut(column):
        return ("case when length(a.{c}) > {n} then left(a.{c}, {n}) || '…' else a.{c} end as {c}").format(
            c=column, n=DESCRIPTION_LIMIT)

    query = """
        select s.*,
               (select string_agg(distinct b.sh_name, ', ') from {schema}.get_list_theme_for_history b
                 where b.id=s.id) as themes
        from (
            select a.id, a.rss, a.name_rss, a.author, a.lang, a.url, a.file, a.error_translator,
                   a.public_date, a.at_date_time,
                   a.title_ru, a.title_en, a.title_he,
                   {desc_ru}, {desc_en}, {desc_he}
            from {schema}.v_nsi_rss_history a
            {where}
            order by coalesce(a.at_date_time, a.public_date) desc
            limit {limit}
        ) s
        order by coalesce(s.at_date_time, s.public_date) desc;
    """.format(schema=config.SCHEMA, where=('where ' + where) if where else '', limit=MAX_ROWS,
               desc_ru=cut('description_ru'), desc_en=cut('description_en'), desc_he=cut('description_he'))
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


def load_day(year, month, day, since_id=''):
    """Новости за сутки (локальное время пользователя); since_id — только новости с id больше (автообновление
    докачивает лишь новые, а не все сутки заново)."""
    tz = get('time_zone') or 0
    date_begin = common.get_date_sql([year, month, day], tz)
    t = datetime.datetime(year, month, day) + datetime.timedelta(days=1)
    date_end = common.get_date_sql([t.year, t.month, t.day], tz)
    return load_news("""(a.public_date is not NULL and a.public_date>='{begin}' and a.public_date<'{end}'
               or a.at_date_time>='{begin}' and a.at_date_time<'{end}')""".format(begin=date_begin, end=date_end)
                     + (' and a.id>{0}'.format(int(since_id)) if since_id else ''))


def load_all(channel, theme, search):
    """Новости без даты (все, самые свежие MAX_ROWS) — фильтры канала, темы и поиска применяются уже в БД, иначе
    браузер фильтровал бы только последние MAX_ROWS новостей. Поиск — по тем же полям, что и в браузере."""
    where = []
    if channel:
        where.append("trim(a.name_rss)='{0}'".format(common.escape_sql_literal(channel)))
    if theme:
        where.append("a.id in (select id from {schema}.get_list_theme_for_history where sh_name='{0}')".format(
            common.escape_sql_literal(theme), schema=config.SCHEMA))
    if search:
        like = common.escape_sql_literal(search.replace('\\', '\\\\').replace('%', r'\%').replace('_', r'\_'))
        where.append("""(concat_ws(' ', a.title_ru, a.title_en, a.title_he, a.description_ru, a.description_en,
                                  a.description_he, a.author, a.name_rss, a.id::text) ilike '%{0}%'
               or a.id in (select id from {schema}.get_list_theme_for_history where sh_name ilike '%{0}%'))""".format(
            like, schema=config.SCHEMA))
    return load_news(' and '.join(where))


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
    """Лента новостей за сутки. POST-поля: st_date (сутки, YYYY-MM-DD; пустая — все новости, тогда в БД
    применяются и фильтры channel, theme, search), find_id (перейти к новости по ID: сутки этой новости,
    par['select_id']), delete_id (удалить новость — только администратор), since_id (автообновление: вернуть
    только новости суток с id больше этого, par['incremental']=True; страница добавляет их к уже загруженным;
    игнорируется при смене суток, переходе к новости и удалении — тогда ответ полный)."""
    answer = dict()
    st = common.init_form(request, '/news_board/')
    if st:
        answer['redirect'] = st
        return answer
    common.default('news_board_st_date', common.local_today())
    st_date = get('news_board_st_date')
    # пользователь смотрел текущие сутки — при возвращении на форму (в т.ч. на следующий день) показываем новые текущие сутки,
    # а не сохранённую в сессии вчерашнюю дату
    if get('news_board_follow_today') and st_date:
        st_date = common.local_today()
    prev_date = st_date
    since_id = ''
    find_id = delete_id = ''
    answer['select_id'] = None
    if request.method == 'POST':
        common.choose_language(request)
        if 'st_date' in request.form:
            # 'today' — текущие сутки пользователя (переход на новые сутки при автообновлении в полночь)
            st_date = common.local_today() if request.form.get('st_date') == 'today' else common.sql_date(request.form.get('st_date'))
        find_id = common.sql_digits(request.form.get('find_id'))
        if find_id:
            found = find_date(find_id)
            if found:
                st_date = found
                answer['select_id'] = int(find_id)
            else:
                answer['not_found'] = int(find_id)
        delete_id = common.sql_digits(request.form.get('delete_id'))
        since_id = common.sql_digits(request.form.get('since_id'))
        if delete_id:
            if common.is_admin():
                cloud.delete_new(delete_id, True)
            else:
                flash('Удалять новости может только администратор', 'warning')
    else:
        common.write_log('Новости (дашборд)', request)
    add('news_board_st_date', st_date)
    add('news_board_follow_today', bool(st_date) and st_date == common.local_today())
    load_list_rss(answer)
    load_themes(answer)
    answer['st_date'] = st_date
    answer['today'] = common.local_today()
    incremental = bool(since_id and st_date and st_date == prev_date and not find_id and not delete_id)
    answer['incremental'] = incremental
    if st_date:
        year, month, day = (int(x) for x in st_date.split('-'))
        answer['data'] = load_day(year, month, day, since_id if incremental else '')
    else:
        form = request.form if request.method == 'POST' else {}
        answer['data'] = load_all(str(form.get('channel') or '').strip(), str(form.get('theme') or '').strip(),
                                  str(form.get('search') or '').strip())
    answer['max_rows'] = MAX_ROWS
    return answer
