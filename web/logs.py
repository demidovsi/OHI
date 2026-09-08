import datetime
import json

from flask import flash

import config
import common
from common import get

array_default = [
    {'key': 'scroll', 'value': 0},
    {'key': 'search', 'value': ''},
    {'key': 'row_count', 'value': 100},
    {'key': 'page', 'value': 1},
    {'key': 'st_date', 'value': common.st_today()},
    {'key': 'switch', 'value': 'one_day'},
    {'key': 'do_update', 'value': True},
    {'key': 'is_today', 'value': True},
]

def get_where(user_id, answer):
    where = common.get_where(answer['search'], ['level', 'source', 'comment', 'law_id', 'file_name'])
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


def get_count_log(user_id, answer):
    try:
        url = 'v1/content/count/{schema}/v_logs?where={where}'.format(
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
        url = 'v1/select/{schema}/v_logs'.format(schema=config.SCHEMA)
        st = get_where(user_id, answer)
        if st != '':
            url = url + '?where=' + st + '&column_order=id desc'
        else:
            url = url + '?column_order=id desc'
        url = url + '&row_count=' + str(row_count) + '&row_from=' + str(row_count * (max(1, page_from) - 1))
        ans, result, status_code = common.send_rest(url)
        if result:
            ans = json.loads(ans)
            time_zone = get(user_id, 'time_zone') or 0
            for unit in ans:
                unit['td'] = common.get_duration(unit['td'])
                # unit['at_date_time'] = datetime.datetime.strptime(unit['at_date_time'], "%Y-%m-%dT%H:%M:%S.%f")
                if unit['at_date_time']:
                    unit['at_date_time'] = common.convert_time_to_timezone(
                        unit['at_date_time'], time_zone,
                        format="%H:%M:%S" if answer['switch'] != 'all_days' else "%Y-%m-%d %H:%M:%S")
            return ans
        else:
            flash(str(ans), 'warning')
            return []
    except Exception as er:
        flash('Ошибка: ' + f"{er}", 'warning')
        return []


def prepare_form(user_id, request):
    answer = dict()
    st = common.init_form(user_id, request, '/logs/')
    if st:
        answer['redirect'] = st
        return answer
    common.default_form(user_id, array_default, answer, 'log_')
    year, month, day = answer['st_date'].split('-')
    if request.method == 'POST':
        common.choose_language(user_id, request)
        common.define_param_for_page(request, answer)
        answer['do_update'] = 'do_update' in request.form

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
            year =datetime.date.today().year
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
        # if 'is_today' in answer and answer['is_today']:
        #     answer['st_date'] = common.st_today()
    else:
        common.write_log('Лог', user_id, request)

    if answer['is_today'] and answer['do_update']:
        # локальная дата на сервере
        year = datetime.date.today().year
        month = datetime.date.today().month
        day = datetime.date.today().day
        # дата с учётом часового пояса пользователя
        date = common.get_date_sql([year, month, day], get(user_id, 'time_zone') or 0)
        year, month, day = date.split(' ')[0].split('-')

    answer['year'] = int(year)
    answer['month'] = int(month)
    answer['day'] = int(day)
    answer['st_date'] = common.get_st_date(year, month, day)
    # answer['is_today'] = answer['st_date'] == common.st_today()

    count = get_count_log(user_id, answer)
    answer['count'] = 0 if count is None else count
    common.define_pages(answer)
    answer['data'] = load_inform(user_id, answer)
    answer['title_search'] = 'OPERATION, SOURCE, LAW_ID, COMMENT, MESSAGE'
    # для возврата в форму из других форм
    common.save_form(user_id, array_default, answer, 'log_')
    return answer
