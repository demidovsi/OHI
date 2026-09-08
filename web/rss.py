import json

from flask import flash

import language
from common import get, add, write_log
import config
import common
import cloud


array_sort = [{"id": "sh_name", "sh_name": 4},
              {"id": "id", "sh_name": 3},
              {"id": "url", "sh_name": 5},
              {"id": "lang", "sh_name": 6},
              {"id": "description", "sh_name": 7},
              {"id": "type_rss", "sh_name": 8},
              {"id": "type_article", "sh_name": 25},
]

array_default = [
    {'key': 'scroll', 'value': 0},
    {'key': 'search', 'value': ''},
    {'key': 'row_count', 'value': 10},
    {'key': 'page', 'value': 1},
    {'key': 'data', 'value': []},
    {'key': 'select_id', 'value': 0},
    {'key': 'selected_sort', 'value': 'id'},
    {'key': 'sort_trend', 'value': 1},
    {'key': 'unit', 'value': {}},
    {'key': 'languages', 'value': language.list_languages},
    {'key': 'filter_language', 'value': ''},
    {'key': 'title', 'value': 2},
    {'key': 'array_sort', 'value': array_sort},
]

def get_where(answer):
   where = common.get_where(answer['search'], ['sh_name', 'url', 'description', 'id::text', 'lang::text', 'type_rss', 'type_article'])
   if answer['filter_language']:
       where = where + ' and ' if where != '' else where
       where = where + "lang='" + answer['filter_language'] + "'"
   return where


def get_count(answer):
    answer['count'] = 0
    where = get_where(answer)
    url = 'v1/count/{schema}/v_nsi_rss_list?type_view=view'.format(schema=config.SCHEMA)
    if where:
        url += '&where=' + where
    ans, is_ok, status = common.send_rest(url)
    if not is_ok:
        flash(str(ans), 'warning')
    else:
        answer['count'] = int(ans)


def get_count_stop(answer):
    answer['count_stop'] = 0
    where = get_where(answer)
    url = 'v1/count/{schema}/v_nsi_rss_list?type_view=view&where=stop'.format(schema=config.SCHEMA)
    if where:
        url += '&where=' + where
    ans, is_ok, status = common.send_rest(url)
    if not is_ok:
        flash(str(ans), 'warning')
    else:
        answer['count_stop'] = int(ans)


def load_inform(answer):
    answer['data'] = []
    row_count = int(answer['row_count'])
    page_from = int(answer['page'])
    try:
        where = get_where(answer)
        url = 'v2/select/{schema}/v_nsi_rss_list?row_count={row_count}&row_from={row_from}'.format(
            schema=config.SCHEMA, row_from=row_count * (max(1, page_from) - 1), row_count=row_count)
        if where:
            url += '&where=' + where
        sort = answer['selected_sort']
        sort = sort + ' desc' if answer['sort_trend'] == 1 else sort
        url += '&column_order=' + sort
        ans, result, status_code = common.send_rest(url)
        if result:
            ans = json.loads(ans)
            answer['data'] = ans
        else:
            flash(str(ans), 'warning')
    except Exception as er:
        flash('Ошибка: ' + f"{er}", 'warning')


def load_rss(answer):
    ans, is_ok, status = common.send_rest('v2/entity/values?app_code={schema}&object_code=rss_list&where=id={id}'.format(
        schema=config.SCHEMA, id=answer['select_id']))
    if not is_ok:
        flash(str(ans), 'warning')
    else:
        ans = json.loads(ans)[0]
        ans['categories'] = ans['categories'] if ans['categories'] else ''
        answer['unit'] = ans
        answer['unit']['sh_name_init'] = answer['unit']['sh_name']
        answer['unit']['url_init'] = answer['unit']['url']
        answer['unit']['lang_init'] = answer['unit']['lang']
        answer['unit']['description_init'] = answer['unit']['description']
        answer['unit']['categories_init'] = answer['unit']['categories']
        answer['unit']['type_rss_init'] = answer['unit']['type_rss']
        answer['unit']['type_article_init'] = answer['unit']['type_article']
        answer['unit']['stop_init'] = answer['unit']['stop']


def check_corr(request, answer):
    for key in request.form.keys():
        if 'corr_obj_' in key:
            st2, st2 = key.split('corr_obj_')
            answer['select_id'] = int(st2)
            load_rss(answer)
            return True
    return False


def check_delete_nsi(user_id, request, answer):
    for key in request.form.keys():
        if 'del_obj_' in key:
            st2, st2 = key.split('del_obj_')
            answer['select_id'] = int(st2)
            load_rss(answer)
            add(user_id, 'page_for_return', '/rss/{user_id}/'.format(user_id=user_id))
            add(user_id, 'delete_source', 'rss')
            add(user_id, 'code', answer['select_id'])
            add(user_id, 'confirmation_text', 'Подтверждение удаления новостной ленты [{name}] с ID={id}'.format(
                name=answer['unit']['sh_name_init'], id=answer['unit']['id']))
            add(user_id, 'question_text',
                'Действительно удалить новостную ленту [{name}] с ID={id} и все ее новости?'.format(
                    name=answer['unit']['sh_name_init'], id=answer['unit']['id']))
            answer['redirect'] = '/delete_unit/{user_id}/'.format(user_id=user_id)
            return True


def check_new_object(request, answer):
    if 'new_object' in request.form:
        answer['unit']['id'] = 0
        answer['select_id'] = 0
        answer['unit']['sh_name'] = ''
        answer['unit']['url'] = ''
        answer['unit']['description'] = ''
        answer['unit']['lang'] = ''
        answer['unit']['type_rss'] = ''
        answer['unit']['type_article'] = ''
        answer['unit']['stop'] = False
        answer['unit']['sh_name_init'] = ''
        answer['unit']['url_init'] = ''
        answer['unit']['description_init'] = ''
        answer['unit']['categories_init'] = ''
        answer['unit']['lang_init'] = ''
        answer['unit']['type_rss_init'] = ''
        answer['unit']['type_article_init'] = ''
        answer['unit']['stop_init'] = False


def check_refresh_nsi(request, answer):
    if 'nsi_refresh' in request.form:
        answer['unit']['sh_name'] = answer['unit']['sh_name_init'] if 'sh_name_init' in answer['unit'] else ''
        answer['unit']['url'] = answer['unit']['url_init'] if 'url_init' in answer['unit'] else ''
        answer['unit']['description'] = answer['unit']['description_init'] if 'description_init' in answer['unit'] else ''
        answer['unit']['categories'] = answer['unit']['categories_init'] if 'categories_init' in answer['unit'] else ''
        answer['unit']['lang'] = answer['unit']['lang_init'] if 'lang_init' in answer['unit'] else ''
        answer['unit']['type_rss'] = answer['unit']['type_rss_init'] if 'type_rss_init' in answer['unit'] else ''
        answer['unit']['type_article'] = answer['unit']['type_article_init'] if 'type_article_init' in answer['unit'] else ''
        answer['unit']['stop'] = answer['unit']['stop_init'] if 'stop_init' in answer['unit'] else False


def define_from_form(answer, request):
    if 'sh_name' in request.form:
        answer['unit']['sh_name'] = request.form['sh_name']
    if 'url' in request.form:
        answer['unit']['url'] = request.form['url']
    if 'description' in request.form:
        answer['unit']['description'] = request.form['description']
    if 'categories' in request.form:
        answer['unit']['categories'] = request.form['categories']
    if 'lang' in request.form:
        answer['unit']['lang'] = request.form['lang']
    if 'type_rss' in request.form:
        answer['unit']['type_rss'] = request.form['type_rss'].strip()
    if 'type_article' in request.form:
        answer['unit']['type_article'] = request.form['type_article'].strip()
    answer['unit']['stop'] = 'stop' in request.form and request.form['stop'] == 'on'


def save_nsi(user_id, answer):
    def slave(code, dat):
        value = answer['unit'][code]
        value = None if value == 'None' else value
        if value:
            value = value.strip()
        values[code] = f"%({code})s"
        dat[code] = value
        return dat

    values = {}
    datas = {}
    datas = slave('sh_name', datas)
    datas = slave('url', datas)
    datas = slave('lang', datas)
    datas = slave('description', datas)
    datas = slave('categories', datas)
    datas = slave('type_rss', datas)
    datas = slave('type_article', datas)
    if 'id' in answer['unit']:
        values['id'] = answer['unit']['id']
    values['stop'] = answer['unit']['stop']

    params = {"schema_name": config.SCHEMA, "object_code": 'rss_list', "values": values, 'datas': datas}
    ans, ok, status = common.send_rest('v3/entity', 'PUT', params=params, token_user=get(user_id, 'token'))
    if not ok:
        flash(str(ans), 'warning')
    else:
        if 'id' in answer['unit'] and answer['unit']['id']:
            operation = 'Произведена коррекция'
        else:
            operation = 'Создание новой'
        common.write_log_db(
            'RSS',
            'Новостные ленты',
            '{operation} новостной ленты;\n '.format(operation=operation) + what_change(answer),
            law_id=answer['unit']['sh_name_init'], page=answer['unit']['id'],
            file_name='Пользователь ' + get(user_id, 'user_address'))
        answer['unit']['sh_name_init'] = answer['unit']['sh_name']
        answer['unit']['url_init'] = answer['unit']['url']
        answer['unit']['lang_init'] = answer['unit']['lang']
        answer['unit']['description_init'] = answer['unit']['description']
        answer['unit']['categories_init'] = answer['unit']['categories']
        answer['unit']['type_rss_init'] = answer['unit']['type_rss']
        answer['unit']['type_article_init'] = answer['unit']['type_article']
        answer['unit']['stop_init'] = answer['unit']['stop']
        answer['unit']['id'] = int(json.loads(ans)[0]['id'])
        return answer['unit']['id']


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
    result = ''
    result += slave('sh_name', 'Имя новостной ленты')
    result += slave('url', 'URL')
    result += slave('description', 'Описание ленты')
    result += slave('categories', 'Категории')
    result += slave('lang', 'Исходный язык')
    result += slave('type_rss', 'Тип ленты')
    result += slave('type_article', 'Тип статей в ленте')
    result += slave('stop', 'Временный останов')
    return result


def delete_rss(user_id, obj_id):
    # прочитать список новостей удаляемой новостной ленты
    ans, is_ok, status = common.send_rest(
        'v2/select/{schema}/nsi_rss_history?where=rss={id} and file is not null and file > 0'.format(
            schema=config.SCHEMA, id=int(obj_id)), params={"columns": "id"})
    if not is_ok:
        flash(str(ans), 'warning')
        return
    list_news = json.loads(ans)  # список новостей, для которых необходимо удалять файлы в облаке
    # удалить новостную ленту
    ans_theme, is_ok, status = common.send_rest(
        'v2/entity/{app_code}/rss_list/{obj_id}/'.format(app_code=config.SCHEMA, obj_id=obj_id), "DELETE",
        token_user=get(user_id, 'token'))
    if not is_ok:
        common.write_log_db(
            'Error', 'Новостные ленты', str(ans_theme) + ' при удалении из БД записи с новостной лентой ID= ' + str(obj_id),
            file_name='Пользователь ' + get(user_id, 'user_address'))
        flash(str(ans_theme), 'warning')
    else:
        for data in list_news:  # удалить файлы новостей
            st = str(data['id'])
            if not cloud.delete_file('en_' + st + '.7z'):
                cloud.delete_file('en_' + st + '.txt')
            if not cloud.delete_file('ru_' + st + '.7z'):
                cloud.delete_file('ru_' + st + '.txt')
            if not cloud.delete_file('he_' + st + '.7z'):
                cloud.delete_file('he_' + st + '.txt')
        common.write_log_db(
            'Удаление новостной ленты', 'Новостные ленты', 'Удалена из БД новостная лента с ID= ' + str(obj_id) + '\n' +
            json.dumps(json.loads(ans_theme), ensure_ascii=False, indent=4),
            file_name='Пользователь ' + get(user_id, 'user_address'))


def prepare_form(user_id, request):
    answer = {}
    redirect_url = common.init_form(user_id, request, '/rss/')
    if redirect_url:
        answer['redirect'] = redirect_url
        return answer

    common.default_form(user_id, array_default, answer, 'rss_')

    if request.method == 'POST':
        common.choose_language(user_id, request)
        common.define_param_for_page(request, answer)
        define_from_form(answer, request)

        if 'filter_language' in request.form:
            answer['filter_language'] = request.form['filter_language']

        if 'refresh_table' in request.form:
            answer['data'] = []

        if check_corr(request, answer):
            common.save_form(user_id, array_default, answer, 'rss_')
            return answer

        if check_new_object(request, answer):
            common.save_form(user_id, array_default, answer, 'rss_')
            return answer

        if check_refresh_nsi(request, answer):
            return answer

        if 'nsi_save' in request.form:
            common.save_form(user_id, array_default, answer, 'rss_')
            save_nsi(user_id, answer)

        if check_delete_nsi(user_id, request, answer):
            common.save_form(user_id, array_default, answer, 'rss_')
            return answer
    else:
        write_log('Новостные ленты', user_id, request)

    get_count(answer)
    get_count_stop(answer)
    load_inform(answer)

    answer['title'] = 2

    common.define_pages(answer)
    common.save_form(user_id, array_default, answer, 'rss_')

    return answer
