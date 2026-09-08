from flask import flash
import config
import common
from common import get
import datetime
import json

array_default = [
    {'key': 'scroll', 'value': 0},
    {'key': 'search', 'value': ''},
    {'key': 'row_count', 'value': 10},
    {'key': 'page', 'value': 1},
    {'key': 'st_date', 'value': common.st_today()},
    {'key': 'switch', 'value': 'one_day'},
    {'key': 'do_update', 'value': True},
    {'key': 'filter_ip', 'value': ''},
    {'key': 'filter_country', 'value': ''},
    {'key': 'filter_city', 'value': ''},
    {'key': 'filter_type_message', 'value': ''},
    {'key': 'filter_email', 'value': ''},
    {'key': 'types_message', 'value': ['', 'sql', 'custom']},
]


def get_where(user_id, answer):
    where = common.get_where(answer['search'], ['ip', 'country', 'city', 'type_message', 'message', 'email'])

    # Фильтры по полям
    if answer['filter_ip']:
        where = where + ' and ' if where != '' else where
        where = where + "ip like '%{value}%'".format(value=answer['filter_ip'])

    if answer['filter_country']:
        where = where + ' and ' if where != '' else where
        where = where + "country like '%{value}%'".format(value=answer['filter_country'])

    if answer['filter_city']:
        where = where + ' and ' if where != '' else where
        where = where + "city like '%{value}%'".format(value=answer['filter_city'])

    if answer['filter_type_message']:
        where = where + ' and ' if where != '' else where
        where = where + "type_message like '%{value}%'".format(value=answer['filter_type_message'])

    if answer['filter_email']:
        where = where + ' and ' if where != '' else where
        where = where + "email like '%{value}%'".format(value=answer['filter_email'])

    # Фильтр по дате
    if answer['switch'] == 'one_day':
        year = answer['year']
        month = answer['month']
        day = answer['day']
        # "or 0" - подстраховка на случай None (напр. вход в обход обычной
        # формы логина, где часовой пояс читается из браузера).
        tz = get(user_id, 'time_zone') or 0
        date_begin = common.get_date_sql([year, month, day], -tz)
        t = datetime.datetime(year, month, day) + datetime.timedelta(days=1)
        date_end = common.get_date_sql([t.year, t.month, t.day], -tz)
        where = where + ' and ' if where != '' else where
        where = where + "at_date_time>='{date_begin}' and at_date_time<'{date_end}'".format(
            date_begin=date_begin, date_end=date_end)
    return where


def get_count_chat_logs(user_id, answer):
    try:
        url = 'v1/content/count/{schema}/chat_logs?where={where}'.format(
            schema=config.SCHEMA, where=get_where(user_id, answer))
        ans, result, status_code = common.send_rest(url)
        if result:
            return int(ans)
        else:
            flash(str(ans), 'warning')
            return 0
    except Exception as er:
        flash('Ошибка: ' + f"{er}", 'warning')
        return 0


def load_inform(user_id, answer):
    row_count = int(answer['row_count'])
    page_from = int(answer['page'])
    try:
        url = 'v2/select/{schema}/chat_logs'.format(schema=config.SCHEMA)
        st = get_where(user_id, answer)
        url += '?where=' + st + '&column_order=id desc' if st else '?column_order=id desc'
        url += f'&row_count={row_count}&row_from={row_count * (max(1, page_from) - 1)}'
        ans, result, status_code = common.send_rest(url)
        if result:
            ans = json.loads(ans)
            for unit in ans:
                if unit['td']:
                    unit['td'] = common.get_duration(unit['td'])
                if unit['at_date_time']:
                    unit['at_date_time'] = datetime.datetime.strptime(unit['at_date_time'].split('.')[0], "%Y-%m-%dT%H:%M:%S")
                # json.dumps нужен только для структурированного ответа
                # (dict/list) - его есть смысл печатать с отступами. Если
                # ответ уже обычная строка (обычный случай для текста от
                # модели), json.dumps лишь портит её: оборачивает в кавычки
                # и экранирует реальные переводы строки в буквальное "\n",
                # из-за чего в textarea/модалке весь текст схлопывался в
                # одну строку с видимыми "\n" вместо настоящих переносов.
                if not isinstance(unit['answer'], str):
                    unit['answer'] = json.dumps(unit['answer'], indent=4, ensure_ascii=False)
            return ans
        else:
            flash(str(ans), 'warning')
            return []
    except Exception as er:
        flash('Ошибка: ' + f"{er}", 'warning')
        return []


def define_pages_data(user_id, answer):
    count = get_count_chat_logs(user_id, answer)
    answer['count'] = 0 if count is None else count
    common.define_pages(answer)
    answer['data'] = load_inform(user_id, answer)


def prepare_form(user_id, request):
    answer = dict()
    st = common.init_form(user_id, request, '/chat_logs/')
    if st:
        answer['redirect'] = st
        return answer
    common.default_form(user_id, array_default, answer, 'chat_log_')
    year, month, day = answer['st_date'].split('-')
    if request.method == 'POST':
        common.choose_language(user_id, request)
        common.define_param_for_page(request, answer)
        answer['do_update'] = 'do_update' in request.form

        # Обработка фильтров
        if 'filter_ip' in request.form:
            answer['filter_ip'] = request.form.get('filter_ip', '').strip()
        if 'filter_country' in request.form:
            answer['filter_country'] = request.form.get('filter_country', '').strip()
        if 'filter_city' in request.form:
            answer['filter_city'] = request.form.get('filter_city', '').strip()
        if 'filter_type_message' in request.form:
            answer['filter_type_message'] = request.form.get('filter_type_message', '').strip()
        if 'filter_email' in request.form:
            answer['filter_email'] = request.form.get('filter_email', '').strip()

        # Кнопка сброса фильтров
        if 'clear_filters' in request.form:
            answer['filter_ip'] = ''
            answer['filter_country'] = ''
            answer['filter_city'] = ''
            answer['filter_type_message'] = ''
            answer['filter_email'] = ''
            answer['page'] = 1
            answer['scroll'] = 0

        if 'dt_start' in request.form and request.form.get('dt_start') != answer['st_date']:
            try:
                year, month, day = request.form.get('dt_start').split('-')
                answer['st_date'] = common.get_st_date(year, month, day)
                answer['do_update'] = True
                answer['scroll'] = 0
            except:
                pass
        if 'one_day' in request.form:
            answer['switch'] = 'one_day'
            answer['do_update'] = answer['st_date'] == common.st_today()
            answer['page'] = 1
            answer['scroll'] = 0
        if 'all_days' in request.form:
            answer['switch'] = 'all_days'
            answer['scroll'] = 0
            answer['page'] = 1
        if 'current_day' in request.form:
            year = datetime.date.today().year
            month = datetime.date.today().month
            day = datetime.date.today().day
            answer['st_date'] = common.get_st_date(year, month, day)
            answer['do_update'] = True
            answer['scroll'] = 0
        elif 'left' in request.form:
            year, month, day = common.calc_day(year, month, day, -1)
            answer['st_date'] = common.get_st_date(year, month, day)
            answer['do_update'] = answer['st_date'] == common.st_today()
            answer['page'] = 1
            answer['scroll'] = 0
        elif 'right' in request.form:
            year, month, day = common.calc_day(year, month, day, 1)
            answer['st_date'] = common.get_st_date(year, month, day)
            answer['do_update'] = answer['st_date'] == common.st_today()
            answer['page'] = 1
            answer['scroll'] = 0
    else:
        common.write_quest(user_id, request, 'ChatLogs')

    answer['st_date'] = common.get_st_date(year, month, day)

    answer['is_today'] = answer['st_date'] == common.st_today()
    answer['year'] = int(year)
    answer['month'] = int(month)
    answer['day'] = int(day)
    define_pages_data(user_id, answer)
    if answer['switch'] == 'all_days':
        format_dt = "HH:mm:ss D.M.Y"
    else:
        format_dt = 'HH:mm:ss'
    answer['format_dt'] = format_dt
    answer['title_search'] = 'Поиск производится по колонкам IP, COUNTRY, CITY, TYPE_MESSAGE, MESSAGE, EMAIL'
    answer['title'] = 'Логи чат-сообщений'
    answer['no_refresh'] = True
    # для возврата в форму из других форм
    common.save_form(user_id, array_default, answer, 'chat_log_')
    return answer
