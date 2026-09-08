import time
import json
from datetime import datetime, timezone

from flask import flash

from common import get, add, write_log
import config
import common
import cloud

array_default = [
    {'key': 'scroll', 'value': 0},
    {'key': 'search', 'value': ''},
    {'key': 'row_count', 'value': 25},
    {'key': 'page', 'value': 1},
    {'key': 'switch', 'value': 'detail'},
    {'key': 'themes', 'value': []},
    {'key': 'data', 'value': []},
    {'key': 'his_data', 'value': []},
    {'key': 'select_theme', 'value': 0},
    {'key': 'global_count', 'value': None},
    {'key': 'selected_sort', 'value': 'rss_history_id'},
    {'key': 'sort_trend', 'value': 1},
    {'key': 'select_id', 'value': 0},
    {'key': 'transcript', 'value': ''},
    {'key': 'len_transcript', 'value': ''},
    {'key': 'labels', 'value': []},
    {'key': 'values', 'value': []},
    {'key': 'unit', 'value': {}},
    {'key': 'date_begin', 'value': '2000-01-01'},
    {'key': 'date_end', 'value': common.calc_st_month(time.gmtime().tm_year, time.gmtime().tm_mon, 1, 1)},
    {'key': 'select_lang', 'value': 'ru'},
    {'key': 'languages', 'value': ['ru', 'en', 'he']},
]

array_sort = [
    {"id": "public_date", "sh_name": 13},
    {"id": "rss_history_id", "sh_name": 14},
]

bucket_name = 'llm-news'


def load_themes(answer):
    ans, is_ok, status = common.send_rest('v2/entity/values?app_code={schema}&object_code=rss_themes'.format(
        schema=config.SCHEMA))
    if not is_ok:
        flash(str(ans), 'warning')
    else:
        answer['themes'] = json.loads(ans)
        answer['themes'] = sorted(answer['themes'], key=lambda p: p['sh_name'], reverse=False)
        for data in answer['themes']:
            data['value'] = common.define_st(data['value'])
            data['exception'] = common.define_st(data['exception'])
            data['sh_name_init'] = data['sh_name']
            data['value_init'] = data['value']
            data['exception_init'] = data['exception']
            data['stop_init'] = data['stop']
        answer['themes'].insert(0, {'id': 0, 'sh_name': '', "value": '', "stop": False, "exception": '',
                                    'sh_name_init': '', "value_init": '', "stop_init": False, "exception_init": ''})
        for data in answer['themes']:
            if data['id'] == answer['select_theme']:
                answer['unit'] = data
                break


def get_count(answer, usl=''):
    answer['count'] = 0
    if answer['select_theme']:
        url = 'v1/count/{schema}/v_rss_history?type_view=view&where=rss_themes_id={id}'.format(
            schema=config.SCHEMA, id=answer['select_theme'])
        if usl:
            url += ' and ' + usl
        ans, is_ok, status = common.send_rest(url)
        if not is_ok:
            flash(str(ans), 'warning')
        else:
            answer['count'] = int(ans)


def load_inform(answer):
    if answer['select_theme']:
        sort = answer['selected_sort']
        if answer['sort_trend'] != 0:
            sort += ' desc'
        url = 'v2/select/{schema}/v_rss_history?where=rss_themes_id={id}&column_order={sort}'.format(
            schema=config.SCHEMA, id=answer['select_theme'], sort=sort)
        url = url + '&row_count=' + str(answer['row_count']) + '&row_from=' + \
              str(answer['row_count'] * (max(1, answer['page']) - 1))
        # if answer['switch'] == 'service':
        #     url += " and public_date >='{date_begin}' and public_date<'{date_end}'".format(
        #         date_begin=answer['date_begin'], date_end=answer['date_end'])
        ans, is_ok, status = common.send_rest(url)
        if not is_ok:
            flash(str(ans), 'warning')
            return []
        else:
            ans = json.loads(ans)
            for data in ans:
                if data['public_date']:
                    data['public_date'] = data['public_date'].split('T')[0]
                else:
                    data['public_date'] = ''
            return ans
    return []


def check_show(request, answer):
    for key in request.form.keys():
        if 'show_' in key:
            st2, st2 = key.split('show_')
            answer['select_id'] = int(st2)
            answer['transcript'] = ''
            return


def check_nsi_refresh(request, answer):
    if 'nsi_refresh' in request.form:
        answer['unit']['sh_name'] = answer['unit']['sh_name_init']
        answer['unit']['value'] = answer['unit']['value_init']
        answer['unit']['exception'] = answer['unit']['exception_init']
        answer['unit']['stop'] = answer['unit']['stop_init']


def define_from_form(answer, request):
    if answer['switch'] == 'service':
        if request.form.get('select_theme') == request.form.get('theme_id'):
            answer['unit']['sh_name'] = request.form.get('nsi_sh_name')
            answer['unit']['value'] = request.form.get('nsi_value')
            answer['unit']['exception'] = request.form.get('nsi_exception')
            answer['unit']['stop'] = 'stop' in request.form and request.form['stop'] == 'on'


def check_new_object(request, answer):
    if 'nsi_new_object' in request.form:
        answer['unit']['sh_name'] = answer['unit']['sh_name_init'] = ''
        answer['unit']['value'] = answer['unit']['value_init'] = ''
        answer['unit']['exception'] = answer['unit']['exception_init'] = ''
        answer['unit']['stop'] = answer['unit']['stop_init'] = False
        answer['unit']['id'] = 0
        answer['select_theme'] = 0
        answer['data'] = []


def make_transcript(user_id, answer):
    txt0 = ''
    ans, is_ok, status = common.send_rest('v2/select/{schema}/v_nsi_rss_history?where=id={id}'.format(
        schema=config.SCHEMA, id=answer['select_id']))
    if not is_ok:
        flash(str(ans), 'warning')
    else:
        ans = json.loads(ans)
        if len (ans) > 0:
            ans = ans[0]
            if ans['author']:
                txt0 += 'author: ' + ans['author'] + '\n\n'
            if ans['title_' + answer['select_lang']]:
                txt0 += '\t' + ans['title_' + answer['select_lang']] + '\n\n'
            if ans['description_' + answer['select_lang']]:
                txt0 += '\t' + ans['description_' + answer['select_lang']] + '\n\n'
    txt = cloud.load_file(user_id, answer['select_lang'] + '_' + str(answer['select_id']))
    answer['transcript'] = txt0 + txt
    answer['len_transcript'] = common.str1000(len(answer['transcript']))


def get_highlight_text(answer):
    answer['select_title'] = ''
    if answer['select_theme']:
        for data in answer['themes']:
            if answer['select_theme'] == data['id']:
                answer['select_title'] = data['value']
                answer['highlight_text'] = answer['select_title'].replace('\n', '').replace('\r', '').split(';')
                for i, unit in enumerate(answer['highlight_text']):
                    if unit:
                        if unit[0] == '^':
                            answer['highlight_text'][i] = ' ' + unit[1:].replace('^', ' ')
                        else:
                            answer['highlight_text'][i] = unit.strip()
                break


def prepare_diagram(answer):
    if answer['switch'] == 'diagram':
        answer['values'] = []
        answer['labels'] = []
        where = "at_date_time>='{date_begin}' and at_date_time<'{date_end}'".format(
            date_begin=answer['date_begin'], date_end=answer['date_end'])
        column_order = 'at_date_time'
        if answer['select_theme']:
            where += ' and rss_themes_id={id}'.format(id=answer['select_theme'])
            column_order = 'sh_name'
        ans, is_ok, status = common.send_rest(
            'v2/select/{schema}/v_counts_themes_date?where={where}&column_order={column_order}'.format(
                schema=config.SCHEMA, where=where, column_order=column_order))
        if not is_ok:
            flash(str(ans), 'warning')
        else:
            ans = json.loads(ans)
            answer['count'] = 0
            if answer['select_theme']:
                for data in ans:
                    answer['values'].append(data['count'])
                    answer['labels'].append(data['at_date_time'])
                    answer['count'] += data['count']
            else:
                for data in ans:
                    if data['sh_name'] in answer['labels']:
                        ind = answer['labels'].index(data['sh_name'])
                        answer['values'][ind] += data['count']
                    else:
                        answer['labels'].append(data['sh_name'])
                        answer['values'].append(data['count'])
                    answer['count'] += data['count']


def what_change(answer):
    def slave(key, caption):
        if key in answer['unit'] and answer['unit'][key] is not None:
            if answer['unit']['id']:
                st = str(answer['unit'][key])
                st_init = str(answer['unit'][key + '_init'])
                if st != st_init:
                    return caption + ' (' + key + '): ' + st_init + ' --> ' + st + ';\n'
                else:
                    return ''
            else:
                return caption + ' (' + key + ')= ' + str(answer['unit'][key]) + ';\n'
        else:
            return ''

    result = slave('value', 'Поисковые образы').replace('\n', ' ') + '\n'
    result += slave('exception', 'Исключения').replace('\n', ' ') + '\n'
    result += slave('sh_name', 'Имя темы')
    result += slave('stop', 'Временный останов')
    return result


def save_nsi(user_id, answer):
    def slave(code):
        value = answer['unit'][code]
        value = None if value == 'None' else value
        if value:
            values[f'{code}'] = f'%({code})s'
            datas[f'{code}'] = value.strip()

    values = {}
    datas = {}
    slave('sh_name')
    slave('value')
    slave('exception')
    if not answer['unit']['id']:
        values['id'] = answer['unit']['id']
        values['inserted_date'] ='%(inserted_date)s'
        datas['inserted_date'] = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    values['stop'] = answer['unit']['stop']

    params = {"schema_name": config.SCHEMA, "object_code": 'rss_themes', "values": values, 'datas': datas}
    ans, ok, status = common.send_rest('v3/entity', 'PUT', params=params, token_user=get(user_id, 'token'))
    if not ok:
        flash(str(ans), 'warning')
    else:
        if answer['unit']['id']:
            operation = 'Произведена коррекция'
        else:
            operation = 'Создание новой'
        common.write_log_db(
            'Поисковые темы',
            'Поисковые образы',
            '{operation} поисковой темы;\n '.format(operation=operation) + what_change(answer),
            law_id=answer['unit']['sh_name_init'],
            file_name='Пользователь ' + get(user_id, 'user_address'))
        answer['unit']['sh_name_init'] = answer['unit']['sh_name']
        answer['unit']['value_init'] = answer['unit']['value']
        answer['unit']['exception_init'] = answer['unit']['exception']
        answer['unit']['stop_init'] = answer['unit']['stop']
        answer['unit']['id'] = int(json.loads(ans)[0]['id'])
        answer['themes'] = []  # перечитать темы
        return answer['unit']['id']


def delete_nsi(user_id, answer):
    add(user_id, 'page_for_return', '/search_words/{user_id}/'.format(user_id=user_id))
    add(user_id, 'delete_source', 'theme')
    add(user_id, 'code', answer['select_theme'])
    add(user_id, 'confirmation_text', 'Подтверждение удаления темы поисковых образов [{name}] с ID={id}'.format(
        name=answer['unit']['sh_name_init'], id=answer['unit']['id']))
    add(user_id, 'question_text',
        'Действительно удалить тему поисковых образов [{name}] с ID={id}?'.format(
            name=answer['unit']['sh_name_init'], id=answer['unit']['id']))
    answer['redirect'] = '/delete_unit/{user_id}/'.format(user_id=user_id)


def delete_theme(user_id, obj_id):
    # прочитать список новостей удаляемой темы
    ans, is_ok, status = common.send_rest(
        'v2/select/{schema}/rel_rss_themes_rss_history_rss'.format(schema=config.SCHEMA))
    if not is_ok:
        flash(str(ans), 'warning')
        return
    list_news = json.loads(ans)  # список всех связок тем и новостей

    # удалить саму тему
    ans_theme, is_ok, status = common.send_rest(
        'v2/entity/{app_code}/rss_themes/{obj_id}/'.format(app_code=config.SCHEMA, obj_id=obj_id), "DELETE",
        token_user=get(user_id, 'token'))
    if not is_ok:
        common.write_log_db(
            'Error', 'Поисковые образы', str(ans_theme) + ' при удалении из БД записи с темой ID= ' + str(obj_id),
            file_name='Пользователь ' + get(user_id, 'user_address'))
        flash(str(ans_theme), 'warning')
        return

    # удаляем из таблицы связей удаляемую тему (это можно не делать, MDM должен сам удалить из таблицы связей)
    query = 'delete from {schema}.rel_rss_themes_rss_history_rss where rss_themes_id={id}'.format(
        schema=config.SCHEMA, id=obj_id)
    ans, is_ok, status = common.send_rest('v2/execute?need_answer=0', 'PUT', params={'script': query},
                                          token_user=get(user_id, 'token'))
    if not is_ok:
        flash(str(ans), 'warning')
        return

    # найдем список новостей (их id) для удаления
    list_id = []
    obj_id = int(obj_id)
    for data in list_news:
        ident = data['rss_history_id']
        count = 0
        for unit in list_news:
            if unit['rss_themes_id'] == obj_id:
                count += 1
        if count == 1:
            list_id.append(ident)

    # удаляем новости, которые только для удаленной темы
    for data in list_id:
        cloud.delete_new(user_id, obj_id), data

    common.write_log_db(
        'Удаление темы', 'Поисковые образы', 'Удалена из БД тема с ID= ' + str(obj_id) + '\n' +
        json.dumps(json.loads(ans_theme), ensure_ascii=False, indent=4),
        file_name='Пользователь ' + get(user_id, 'user_address'))
    add(user_id, 'search_words_data', [])
    add(user_id, 'search_words_themes', [])


def define_month(answer, delta):
    year, month, day = answer['date_begin'].split('-')
    answer['date_begin'] = common.calc_st_month(year, month, day, delta)
    answer['date_begin'] = max(answer['date_begin'], '2000-01-01')
    year, month, day = answer['date_end'].split('-')
    answer['date_end'] = common.calc_st_month(year, month, day, delta)
    answer['date_end'] = max(answer['date_end'], '2000-02-01')


def current_month(answer, delta):
    year = time.gmtime().tm_year
    month = time.gmtime().tm_mon
    answer['date_begin'] = common.calc_st_month(year, month, 1, delta)
    answer['date_end'] = common.calc_st_month(year, month, 1, 1 + delta)


def load_history(answer):
    if answer['select_theme']:
        url = 'v2/select/{schema}/v_rss_history?where=rss_themes_id={id}'.format(
            schema=config.SCHEMA, id=answer['select_theme'])
        if answer['switch'] == 'service':
            url += " and at_date_time >='{date_begin}' and at_date_time<'{date_end}'".format(
                date_begin=answer['date_begin'], date_end=answer['date_end'])
        url = url + '&row_count=' + str(answer['row_count']) + '&row_from=' + \
              str(answer['row_count'] * (max(1, answer['page']) - 1)) + '&column_order=rss_history_id'
        ans, is_ok, status = common.send_rest(url)
        if not is_ok:
            flash(str(ans), 'warning')
            return []
        else:
            ans = json.loads(ans)
            for data in ans:
                if data['public_date']:
                    data['public_date'] = data['public_date'].split('T')[0]
            return ans
    return []


def prepare_history(answer):
    if answer['switch'] == 'service':
        if answer['select_theme']:
            get_count(answer)
            answer['global_count'] = answer['count']
            usl = "at_date_time>='{date_begin}' and at_date_time<'{date_end}'".format(
                date_begin=answer['date_begin'], date_end=answer['date_end'])
            get_count(answer, usl)
            if len(answer['his_data']) == 0 or 'change_page' in answer and answer['change_page']:
                answer['his_data'] = load_history(answer)
            answer['no_refresh'] = True
        else:

            answer['his_data'] = []
            answer['count'] = 0
            answer['global_count'] = 0


def save_history(user_id, answer, request):
    if answer['switch'] == 'service' and answer['select_theme']:
        if request.form.get('his_date'):
            url = 'v1/MDM/his/{schema}/rss_themes/counts/{obj_id}'.format(
                schema=config.SCHEMA, obj_id=answer['unit']['id'])
            dt = request.form.get('his_date')
            url += "?dt={dt}&value={value}".format(dt=dt, value=request.form.get('his_value'))
            ans, is_ok, status = common.send_rest(url, 'POST', token_user=get(user_id, 'token'))
            if not is_ok:
                flash(str(ans), 'warning')
            else:
                answer['his_data'] = []  # перечитать данные с новым значением
                answer['his_date'] = ''
                answer['his_value'] = ''
        else:
            flash('Необходимо задать дату и время для значения', 'warning')


def check_delete(answer, request, user_id):
    # удаление новости из темы
    for key in request.form.keys():
        if 'his_delete_' in key:
            st2, st2 = key.split('his_delete_')
            for unit in answer['his_data']:
                if unit['rss_history_id'] == int(st2):
                    # прочитать список тем, которым принадлежит удаляемая новость
                    ans, is_ok, status = common.send_rest(
                        'v2/select/{schema}/rel_rss_themes_rss_history_rss?where=rss_history_id={id}'.format(
                            schema=config.SCHEMA, id=st2))
                    if not is_ok:
                        flash(str(ans), 'warning')
                        return
                    list_themes = json.loads(ans)
                    # удалить ссылки на новость в таблице связи
                    query = ("delete from {schema}.rel_rss_themes_rss_history_rss "
                             "where rss_history_id={id} and rss_themes_id={theme}").format(
                        schema=config.SCHEMA, id=st2, theme=answer['select_theme'])
                    ans, is_ok, status = common.send_rest(
                        'v2/execute?need_answer=0', 'PUT', params={"script": query},
                        token_user=get(user_id, 'token'))
                    if not is_ok:
                        flash(str(ans), 'warning')
                        return
                    # выясним нужно ли удалять новости удаляемой темы, которые входят в еще и другие темы
                    need = True
                    for data in list_themes:
                        if data['rss_themes_id'] != answer['select_theme']:
                            need = False
                            break
                    if need:  # нужно удалить новость
                        cloud.delete_new(user_id, st2, True)
                    mes = 'Удалена новость {id}'.format(id=st2)
                    if need:
                        mes += ' с удалением и самой новости'
                    else:
                        mes += ' без удаления самой новости, так как новость присутствует в других темах'
                    common.write_log_db(
                        'Удаление новости из темы', 'Поисковые образы', mes,
                        file_name='Пользователь ' + get(user_id, 'user_address'))
                    answer['his_data'] = []
                    answer['data'] = []
                break


def clear_history(user_id, answer):
    obj_id = answer['select_theme']
    # прочитать список новостей очищаемой темы
    ans, is_ok, status = common.send_rest(
        'v2/select/{schema}/rel_rss_themes_rss_history_rss?where=rss_themes_id={id}'.format(
            schema=config.SCHEMA, id=obj_id))
    if not is_ok:
        flash(str(ans), 'warning')
        return
    list_news = json.loads(ans)
    # удалить тему из таблицы связи
    query = 'delete from {schema}.rel_rss_themes_rss_history_rss where rss_themes_id={id}'.format(
        schema=config.SCHEMA, id=obj_id)
    ans, is_ok, status = common.send_rest('v2/execute?need_answer=0', 'PUT', params={'script': query},
                                          token_user=get(user_id, 'token'))
    if not is_ok:
        flash(str(ans), 'warning')
        return
    # выясним нужно ли удалять новости удаляемой темы, которые входят в еще и другие темы
    need = False
    for data in list_news:
        if data['rss_themes_id'] != int(obj_id):
            need = True
            break
    if need:  # нужно удалять новости с id из списка
        query = ''
        for data in list_news:
            query = query + ',' if query else query
            query += str(data['rss_history_id'])
        query = 'delete from {schema}.nsi_rss_history where id in ({query})'.format(schema=config.SCHEMA, query=query)
        ans, is_ok, status = common.send_rest('v2/execute?need_answer=0', 'PUT', params={'script': query},
                                              token_user=get(user_id, 'token'))
        if not is_ok:
            flash(str(ans), 'warning')

    common.write_log_db(
        'Поисковые темы', 'Удаление данных',
        'Удалены исторические данные в количестве {count} для темы [{name}]'.format(
            count=answer['global_count'], name=answer['unit']['sh_name_init']),
        file_name='Пользователь ' + get(user_id, 'user_address'))
    answer['his_data'] = []
    answer['data'] = []
    return True


def history_start(user_id, answer):
    if clear_history(user_id, answer):
        dt = 'NULL'
        ans, ok, status = common.send_rest(
            "v1/update/{schema}/rss_themes?where=id={id}".format(schema=config.SCHEMA, id=answer['unit']['id']),
            'PATCH', token_user=common.get(user_id, 'token'),
            params={"values": {"last_date": f'{dt}'}})
        if not ok:
            flash(str(answer), 'warning')
        else:
            answer['themes'] = []


def prepare_form(user_id, request):
    answer = dict()
    st = common.init_form(user_id, request, '/search_words/')
    if st:
        answer['redirect'] = st
        return answer
    common.default_form(user_id, array_default, answer, 'search_words_')
    if request.method == 'POST':
        common.choose_language(user_id, request)
        common.define_param_for_page(request, answer)
        define_from_form(answer, request)
        if 'select_lang' in request.form:
            answer['select_lang'] = request.form.get('select_lang')
            answer['transcript'] = ''
        if 'detail' in request.form:
            answer['switch'] = 'detail'
        if 'diagram' in request.form:
            answer['switch'] = 'diagram'
        if 'service' in request.form:
            answer['switch'] = 'service'
        if 'refresh_table' in request.form:
            answer['data'] = []
        if 'select_theme' in request.form and answer['select_theme'] != int(request.form.get('select_theme')):
            answer['select_theme'] = int(request.form.get('select_theme'))
            answer['transcript'] = ''
            answer['data'] = []
            answer['his_data'] = []
            answer['select_id'] = 0
            for data in answer['themes']:
                if data['id'] == answer['select_theme']:
                    answer['unit'] = data
                    break
        check_show(request, answer)
        check_nsi_refresh(request, answer)
        check_new_object(request, answer)
        check_delete(answer, request, user_id)
        if 'nsi_save' in request.form:
            save_nsi(user_id, answer)
        if 'nsi_delete' in request.form:
            delete_nsi(user_id, answer)
        if 'refresh' in request.form:
            answer['transcript'] = ''  # Прочитать текст стенограммы
            answer['data'] = []  # прочитать все даты
            answer['themes'] = []  # перечитать темы
        if 'date_begin' in request.form and answer['date_begin'] != max(request.form.get('date_begin'), '2000-01-01'):
            answer['date_begin'] = max(request.form.get('date_begin'), '2000-01-01')
            answer['page'] = 1
            answer['his_data'] = []
        if 'date_end' in request.form and answer['date_end'] != max(request.form.get('date_end'), '2000-02-01'):
            answer['date_end'] = max(request.form.get('date_end'), '2000-02-01')
            answer['page'] = 1
            answer['his_data'] = []
        if 'left_history' in request.form:
            define_month(answer, -1)
            answer['page'] = 1
            answer['his_data'] = []
        if 'right_history' in request.form:
            define_month(answer, 1)
            answer['page'] = 1
            answer['his_data'] = []
        if 'current_month' in request.form:
            current_month(answer, 0)
            answer['his_data'] = []
            answer['page'] = 1
        if 'previous_month' in request.form:
            current_month(answer, -1)
            answer['his_data'] = []
            answer['page'] = 1
        if 'his_all' in request.form:
            answer['date_begin'] = '2000-01-01'
            answer['date_end'] = common.st_today()
            answer['his_data'] = []
        answer['his_date'] = request.form.get('his_date')
        answer['his_value'] = request.form.get('his_value')
        for key in request.form.keys():
            if 'corr_' in key:
                st2, st2 = key.split('corr_')
                for unit in answer['his_data']:
                    if unit['dt'] == st2:
                        answer['his_date'] = st2
                        answer['his_value'] = unit['value']
                        break
        if 'save_history' in request.form:
            save_history(user_id, answer, request)
        if 'his_clear' in request.form:
            clear_history(user_id, answer)
        if 'his_start' in request.form:
            history_start(user_id, answer)
    else:
        write_log('Поисковые образы', user_id, request)

    if len(answer['themes']) == 0:
        load_themes(answer)
        answer['select_theme'] = 0
        for data in answer['themes']:
            if data['id'] == answer['select_theme']:
                answer['unit'] = data
                answer['select_theme'] = data['id']
                break
    if answer['switch'] == 'detail':
        get_count(answer)
        answer['global_count'] = answer['count']
        answer['data'] = load_inform(answer)
        if answer['select_id'] and answer['transcript'] == '':
            make_transcript(user_id, answer)
    prepare_diagram(answer)
    prepare_history(answer)
    answer['array_sort'] = array_sort
    answer['no_search'] = True
    get_highlight_text(answer)
    # answer['no_refresh'] = True
    common.define_pages(answer)
    common.save_form(user_id, array_default, answer, 'search_words_')
    return answer
