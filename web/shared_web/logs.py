"""Общая форма сайтов («Log», /logs/: журнал v_logs схемы сайта) — один код для всех сайтов parlaments (sozd-web, kns-web, ...).

Сайт отличается только схемой БД и меткой журнала: модуль работает с модулями того сайта, в котором запущен —
`config` (SCHEMA, LOG_SRC) и `common` (сессия, REST, журнал, помощники форм), см. shared_web/README.md.
"""
from flask import flash
import config
import common
from common import get
import datetime
import json

array_default = [
    {'key': 'scroll', 'value': 0},
    {'key': 'search', 'value': ''},
    {'key': 'search_level', 'value': ''},
    {'key': 'search_source', 'value': ''},
    {'key': 'search_who', 'value': ''},
    {'key': 'row_count', 'value': 100},
    {'key': 'page', 'value': 1},
    {'key': 'st_date', 'value': common.st_today()},
    {'key': 'switch', 'value': 'one_day'},
    {'key': 'do_update', 'value': True},
]


def local_today():
    """'Сегодня' по локальному времени пользователя (его time_zone), а не UTC/времени сервера —
    нужно, чтобы смена суток в режиме автообновления происходила в правильный момент для пользователя."""
    tz = get('time_zone') or 0
    local_now = datetime.datetime.utcnow() + datetime.timedelta(hours=tz)
    return common.get_st_date(local_now.year, local_now.month, local_now.day)


# Поисковые образы: поле формы -> колонка v_logs (search - только по Message).
SEARCH_COLUMNS = [
    ('search', 'comment'),
    ('search_level', 'level'),
    ('search_source', 'source'),
    ('search_who', 'law_id'),
]


def get_where(answer):
    where = ' and '.join(filter(None, (
        common.get_where(answer[key], [column]) for key, column in SEARCH_COLUMNS)))
    if answer['switch'] == 'one_day':
        year = answer['year']
        month = answer['month']
        day = answer['day']
        date_begin = common.get_date_sql([year, month, day], get('time_zone'))
        t = datetime.datetime(year, month, day) + datetime.timedelta(days=1)
        date_end = common.get_date_sql([t.year, t.month, t.day], get('time_zone'))
        where = where + ' and ' if where != '' else where
        where = where + "at_date_time>='{date_begin}' and at_date_time<'{date_end}'".format(
            date_begin=date_begin, date_end=date_end)
    return where


def get_count_log(answer):
    try:
        url = 'v1/content/count/{schema}/v_logs?where={where}'.format(
            schema=config.SCHEMA, where=get_where(answer))
        ans, result, status_code = common.send_rest(url)
        if result:
            return int(ans)
        else:
            flash(str(ans), 'warning')
            return 0
    except Exception as er:
        flash('Ошибка: ' + f"{er}", 'warning')
        return 0


def load_inform(answer):
    row_count = int(answer['row_count'])
    page_from = int(answer['page'])
    try:
        url = 'v2/select/{schema}/v_logs'.format(schema=config.SCHEMA)
        st = get_where(answer)
        url += '?where=' + st + '&column_order=id desc' if st else '?column_order=id desc'
        url += f'&row_count={row_count}&row_from={row_count * (max(1, page_from) - 1)}'
        ans, result, status_code = common.send_rest(url)
        if result:
            ans = json.loads(ans)
            for unit in ans:
                unit['td'] = common.get_duration(unit['td'])
                unit['at_date_time'] = datetime.datetime.strptime(unit['at_date_time'], "%Y-%m-%dT%H:%M:%S.%f")
            return ans
        else:
            flash(str(ans), 'warning')
            return []
    except Exception as er:
        flash('Ошибка: ' + f"{er}", 'warning')
        return []


def define_pages_data(answer):
    count = get_count_log(answer)
    answer['count'] = 0 if count is None else count
    common.define_pages(answer)
    answer['data'] = load_inform(answer)


def prepare_form(request):
    answer = dict()
    st = common.init_form(request, '/logs/')
    if st:
        answer['redirect'] = st
        return answer
    common.default_form(array_default, answer, 'log_')
    year, month, day = answer['st_date'].split('-')
    if request.method == 'POST':
        common.choose_language(request)
        common.define_param_for_page(request, answer)
        answer['do_update'] = 'do_update' in request.form
        changed_search = answer['change_search']
        for key in ('search_level', 'search_source', 'search_who'):
            if key in request.form and request.form.get(key) != answer[key]:
                answer[key] = request.form.get(key)
                changed_search = True
        if changed_search:
            answer['page'] = 1
            answer['scroll'] = 0

        if 'dt_start' in request.form and request.form.get('dt_start') != answer['st_date']:
            try:
                year, month, day = request.form.get('dt_start').split('-')
                answer['st_date'] = common.get_st_date(year, month, day)
                # автообновление — только для текущих суток (иначе блок ниже вернёт дату на сегодня)
                answer['do_update'] = answer['st_date'] == local_today()
                answer['page'] = 1
                answer['scroll'] = 0
            except:
                pass
        if 'one_day' in request.form:
            answer['switch'] = 'one_day'
            answer['do_update'] = answer['st_date'] == local_today()
            answer['page'] = 1
            answer['scroll'] = 0
        if 'all_days' in request.form:
            answer['switch'] = 'all_days'
            answer['scroll'] = 0
            answer['page'] = 1
        if 'current_day' in request.form:
            year, month, day = local_today().split('-')
            answer['st_date'] = common.get_st_date(year, month, day)
            answer['do_update'] = True
            answer['scroll'] = 0
        elif 'left' in request.form:
            year, month, day = common.calc_day(year, month, day, -1)
            answer['st_date'] = common.get_st_date(year, month, day)
            answer['do_update'] = answer['st_date'] == local_today()
            answer['page'] = 1
            answer['scroll'] = 0
        elif 'right' in request.form:
            year, month, day = common.calc_day(year, month, day, 1)
            answer['st_date'] = common.get_st_date(year, month, day)
            answer['do_update'] = answer['st_date'] == local_today()
            answer['page'] = 1
            answer['scroll'] = 0
    else:
        common.write_log('Log', request)

    # Режим автообновления работает только для текущих суток. Если локальные сутки уже сменились
    # (например, страница/автообновление были открыты через полночь) — переходим на новые сутки,
    # не сбрасывая сам режим автообновления.
    if answer['switch'] == 'one_day' and answer['do_update']:
        today_local = local_today()
        if answer['st_date'] != today_local:
            year, month, day = today_local.split('-')
            answer['page'] = 1
            answer['scroll'] = 0

    answer['st_date'] = common.get_st_date(year, month, day)

    answer['is_today'] = answer['st_date'] == local_today()
    answer['year'] = int(year)
    answer['month'] = int(month)
    answer['day'] = int(day)
    define_pages_data(answer)
    if answer['switch'] == 'all_days':
        format_dt = "HH:mm:ss D.M.Y"
    else:
        format_dt = 'HH:mm:ss'
    answer['format_dt'] = format_dt
    answer['search_label'] = 'Message: '
    answer['title_search'] = 'Поиск (фильтрация) производится по колонке MESSAGE'
    answer['extra_searches'] = [
        {'name': 'search_level', 'label': 'Operation: ', 'value': answer['search_level'],
         'title': 'Поиск (фильтрация) производится по колонке OPERATION'},
        {'name': 'search_source', 'label': 'Source: ', 'value': answer['search_source'],
         'title': 'Поиск (фильтрация) производится по колонке SOURCE'},
        {'name': 'search_who', 'label': 'Who: ', 'value': answer['search_who'],
         'title': 'Поиск (фильтрация) производится по колонке WHO/WHERE'},
    ]
    answer['title'] = 'Содержимое лог файла'
    answer['ajax_form'] = True
    # для возврата в форму из других форм
    common.save_form(array_default, answer, 'log_')
    return answer
