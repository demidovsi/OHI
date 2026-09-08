import copy
import json

from flask import flash

import common as cd
import config
from common import get

array_default = [
    {'key': 'scroll', 'value': 0},
    {'key': 'name_function', 'value': ''},
    {'key': 'description_function', 'value': ''},
    {'key': 'data', 'value': []},
    {'key': 'data_init', 'value': []},
    {'key': 'functions', 'value': []},
]


def load_data(answer):
    url = 'v2/select/{schema}/nsi_parser_functions?column_order=sh_name'.format(schema=config.SCHEMA)
    ans, is_ok, status_code = cd.send_rest(url)
    if is_ok:
        answer['functions'] = json.loads(ans)
    else:
        flash(str(ans), 'warning')
        return
    url = "v2/select/{schema}/v_nsi_functions_params?type_view=view&column_order=name_function, code".format(
        schema=config.SCHEMA)
    ans, is_ok, status_code = cd.send_rest(url)
    if is_ok:
        ans = json.loads(ans)
        # Показать имя/описание функции только у первой строки её параметров -
        # остальные строки той же функции получают пустой name_function.
        seen_name_functions = set()
        for unit in ans:
            unit['init_value'] = unit['value']
            unit['sh_name'] = unit['sh_name'] if unit['sh_name'] else ''
            name_function = unit['name_function']
            if name_function != '':
                if name_function in seen_name_functions:
                    unit['name_function'] = ''
                else:
                    seen_name_functions.add(name_function)
        for unit in answer['functions']:
            for data in ans:
                if unit['id'] == data['function']:
                    data['description'] = unit['description'] or ''
                    break
        function_ids = {unit['id'] for unit in answer['functions']}
        ans = [row for row in ans if row['function'] in function_ids]
        answer['data'] = ans
        answer['data_init'] = copy.deepcopy(answer['data'])
    else:
        flash(str(ans), 'warning')
        answer['data'] = []
        answer['data_init'] = copy.deepcopy(answer['data'])


def save(user_id, answer):
    for i, data in enumerate(answer['data']):
        if data['name_function']:
            st = cd.what_change(answer['data'][i], answer['data_init'][i], ['name_function', 'description'])
            if st:
                function_id = data['function']
                make_corr_function(user_id, answer, function_id)
        st = cd.what_change(answer['data'][i], answer['data_init'][i])
        if st:  # есть изменения
            parameter_id = data['id']
            make_corr_parameter(user_id, answer, parameter_id)


def get_from_form(request, answer):
    """Читает данные из POST-формы и обновляет answer['data'].

    Схема имён полей таблицы:
      val~{id}       — значение параметра
      code~{id}      — код параметра
      sh_name~{id}   — комментарий параметра
      is_number~{id} — признак числового значения (checkbox)
      function_name~{function_id} — имя функции (первый параметр группы)
      function_description~{function_id} — описание функции (первый параметр группы)
    """
    load_data(answer)
    for unit in answer['data']:
        uid = str(unit['id'])
        unit['value'] = request.form.get(f'val~{uid}', unit['value'])
        unit['code'] = request.form.get(f'code~{uid}', unit['code'])
        unit['sh_name'] = request.form.get(f'sh_name~{uid}', unit['sh_name'])
        unit['is_number'] = 1 if f'is_number~{uid}' in request.form else 0
        if unit['name_function']:
            fid = str(unit['function'])
            unit['name_function'] = request.form.get(f'function_name~{fid}', unit['name_function'])
            unit['description'] = request.form.get(f'function_description~{fid}', unit['description'])

    # Поля диалога создания новой функции
    answer['name_function'] = request.form.get('name_function', answer.get('name_function', ''))
    answer['description_function'] = request.form.get('description_function', answer.get('description_function', ''))


def get_name_function_by_id(answer, function_id):
    for data in answer['functions']:
        if str(data['id']) == str(function_id):
            return data['sh_name']
    return ''


def make_corr_function(user_id, answer, function_id):
    for i, data in enumerate(answer['data']):
        if data['function'] == function_id and data['name_function']:
            values = {"sh_name": '%(sh_name)s', "description": '%(description)s', "id": function_id}
            datas = {
                "sh_name": data['name_function'],
                "description": data['description']
            }
            operation = 'Коррекция'
            params = {"schema_name": config.SCHEMA, "object_code": "parser_functions", "values": values, "datas": datas}
            ans, ok, status = cd.send_rest('v3/entity', 'PUT', params=params, token_user=get(user_id, 'token'))
            if not ok:
                flash(str(ans) + '\n' + json.dumps(params, indent=4, ensure_ascii=False), 'warning')
            else:
                cd.write_log_db(operation + ' функции', 'functions',
                                cd.what_change(answer['data_init'][i], answer['data'][i],
                                               ['name_function', 'description']),
                                law_id=answer['data_init'][i]['name_function'],
                                file_name=get(user_id, 'user_address'))
                new_sh_name = datas['sh_name']
                new_description = datas['description']
                for func in answer['functions']:
                    if func['id'] == function_id:
                        func['sh_name'] = new_sh_name
                        func['description'] = new_description
                        break
                answer['data_init'][i] = copy.deepcopy(answer['data'][i])


def check_corr_function(user_id, request, answer):
    for key in request.form.keys():
        if key.startswith('corr_function_'):
            function_id = int(key[len('corr_function_'):])
            make_corr_function(user_id, answer, function_id)
            break


def make_corr_parameter(user_id, answer, parameter_id):
    for i, data in enumerate(answer['data']):
        if data['id'] == parameter_id:
            values = {"sh_name": data['sh_name'],
                      "code": data['code'],
                      "value": data['value'],
                      "id": parameter_id,
                      "is_number": data['is_number']
                      }
            params = {"schema_name": config.SCHEMA, "object_code": "functions_params", "values": values}
            ans, ok, status = cd.send_rest('v3/entity', 'PUT', params=params, token_user=get(user_id, 'token'))
            if not ok:
                flash(str(ans) + '\n' + json.dumps(params, indent=4, ensure_ascii=False), 'warning')
            else:
                cd.write_log_db(
                    'Коррекция параметра функции', 'functions',
                    cd.what_change(answer['data_init'][i], answer['data'][i]),
                    law_id=get_name_function_by_id(answer, data['function']) + '.' + answer['data_init'][i]['code'],
                    file_name=get(user_id, 'user_address'))
                answer['data_init'][i] = copy.deepcopy(answer['data'][i])


def check_corr_parameter(user_id, request, answer):
    for key in request.form.keys():
        if key.startswith('corr_parameter_'):
            parameter_id = int(key[len('corr_parameter_'):])
            make_corr_parameter(user_id, answer, parameter_id)
            break


def create_function(user_id, answer):
    operation = 'Создание'
    values = {"sh_name": '%(sh_name)s', "description": '%(description)s'}
    datas = {"sh_name": answer['name_function'], "description": answer['description_function']}
    params = {"schema_name": config.SCHEMA, "object_code": "parser_functions", "values": values, "datas": datas}
    ans, ok, status = cd.send_rest('v3/entity', 'PUT', params=params, token_user=get(user_id, 'token'))
    if not ok:
        flash(str(ans), 'warning')
    else:
        cd.write_log_db(operation + ' функции', 'functions', str(datas), law_id=answer['name_function'],
                        file_name=get(user_id, 'user_address'))
        try:
            new_id = int(json.loads(ans)[0]['id'])
        except Exception:
            new_id = 0
        new_func = {'id': new_id, 'sh_name': answer['name_function'], 'description': answer['description_function']}
        answer['functions'].append(new_func)
        answer['data'].append({
            'name_function': answer['name_function'],
            'function': new_id,
            'id': f"new_{new_id}",
            'code': '',
            'value': '',
            'sh_name': '',
            'is_number': 0,
            'description': answer['description_function'],
            'init_value': '',
            'is_placeholder': True,
        })
        answer['data_init'] = copy.deepcopy(answer['data'])
        answer['name_function'] = ''
        answer['description_function'] = ''


def create_parameter(user_id, request, answer):
    fid = int(request.form.get('dlg_select_function', 0) or 0)
    code = (request.form.get('dlg_code_parameter') or '').strip()
    if fid <= 0 or not code:
        flash('Не выбрана функция или не указан код параметра', 'warning')
        return
    values = {"sh_name": request.form.get('dlg_comment_parameter'),
              "code": code,
              "function": fid,
              "is_number": 'dlg_is_number_parameter' in request.form.keys()
              }
    params = {"schema_name": config.SCHEMA, "object_code": "functions_params", "values": values}
    ans, ok, status = cd.send_rest('v3/entity', 'PUT', params=params, token_user=get(user_id, 'token'))
    if not ok:
        flash(str(ans) + '\n' + json.dumps(params, indent=4, ensure_ascii=False), 'warning')
    else:
        cd.write_log_db('Создание параметра функции', 'functions', str(values),
                        law_id=get_name_function_by_id(answer, fid) + '.' + code,
                        file_name=get(user_id, 'user_address'))
        try:
            new_id = int(json.loads(ans)[0]['id'])
        except Exception:
            new_id = 0
        new_row = {
            'function': fid,
            'id': new_id,
            'code': code,
            'value': '',
            'sh_name': request.form.get('dlg_comment_parameter'),
            'is_number': 'dlg_is_number_parameter' in request.form.keys(),
            'description': '',
            'init_value': ''
        }
        for i, row in enumerate(answer['data']):
            if row.get('function') == fid:
                if not row.get('code'):
                    new_row['name_function'] = row['name_function']
                    new_row['description'] = row['description']
                    answer['data'][i] = new_row
                else:
                    new_row['name_function'] = ''
                    answer['data'].insert(i + 1, new_row)
                break
        answer['data_init'] = copy.deepcopy(answer['data'])


def check_delete_function(user_id, request, answer):
    for key in request.form.keys():
        if key.startswith('delete_function_'):
            function_id = int(key[len('delete_function_'):])
            code_service = get_name_function_by_id(answer, function_id)
            url = 'v2/entity/{app_code}/parser_functions/{object_id}'.format(
                object_id=function_id, app_code=config.SCHEMA)
            ans, ok, status_answer = cd.send_rest(url, 'DELETE', token_user=get(user_id, 'token'))
            if ok:
                cd.write_log_db('Удаление функции', 'functions',
                                f'Сервис [{code_service}]\nfunction_id={function_id}',
                                file_name=get(user_id, 'user_address'))
                answer['functions'] = [f for f in answer['functions'] if f['id'] != function_id]
                answer['data'] = [d for d in answer['data'] if d.get('function') != function_id]
                answer['data_init'] = copy.deepcopy(answer['data'])
            else:
                flash(str(ans), 'warning')
            break


def check_delete_parameter(user_id, request, answer):
    for key in request.form.keys():
        if key.startswith('delete_parameter_'):
            parameter_id = int(key[len('delete_parameter_'):])
            code_parameter = ''
            code_function = ''
            value = ''
            function = 0
            for unit in answer['data']:
                if unit['id'] == parameter_id:
                    code_parameter = unit['code']
                    function = unit['function']
                    value = unit['value']
                    break
            if function:
                for unit in answer['data']:
                    if unit['function'] == function and unit['name_function']:
                        code_function = unit['name_function']
                        break

            url = 'v2/entity/{app_code}/functions_params/{object_id}'.format(
                object_id=parameter_id, app_code=config.SCHEMA)
            ans, ok, status_answer = cd.send_rest(url, 'DELETE', token_user=get(user_id, 'token'))
            if ok:
                cd.write_log_db('Удаление параметра функции', 'functions',
                                f'Функция [{code_function}], Параметр [{code_parameter}], Значение [{value}]\n'
                                f'function_id={function}, parameter_id={parameter_id}',
                                file_name=get(user_id, 'user_address'))
                for i, unit in enumerate(answer['data']):
                    if unit['function'] == function and unit['id'] == parameter_id:
                        next_is_same = (i + 1 < len(answer['data']) and
                                        answer['data'][i + 1]['function'] == function)
                        if unit['name_function'] and next_is_same:
                            # передать имя функции следующей строке
                            answer['data'][i + 1]['name_function'] = unit['name_function']
                            answer['data'][i + 1]['description'] = unit.get('description', '')
                            answer['data'].pop(i)
                        elif unit['name_function'] and not next_is_same:
                            # единственный параметр — заменить на placeholder
                            answer['data'][i] = {
                                'name_function': unit['name_function'],
                                'function': function,
                                'id': f"new_{function}",
                                'code': '',
                                'value': '',
                                'sh_name': '',
                                'is_number': 0,
                                'description': unit.get('description', ''),
                                'init_value': '',
                                'is_placeholder': True,
                            }
                        else:
                            answer['data'].pop(i)
                        break
                answer['data_init'] = copy.deepcopy(answer['data'])
            else:
                flash(str(ans), 'warning')
            break


def prepare_form(user_id, request):
    answer = dict()
    st = cd.init_form(user_id, request, '/functions/')  # проверить наличие user_id
    if st:  # необходимо делать login
        answer['redirect'] = st
        return answer
    cd.default_form(user_id, array_default, answer, 'function_')
    if request.method == 'POST':
        cd.choose_language(user_id, request)
        if 'scroll' in request.form and request.form.get('scroll'):
            answer['scroll'] = float(request.form.get('scroll'))
        get_from_form(request, answer)  # прочитать данные из БД и изменить их данными с формы
        if 'create_function' in request.form:
            create_function(user_id, answer)
        if 'create_parameter' in request.form:
            create_parameter(user_id, request, answer)
        check_delete_function(user_id, request, answer)
        check_delete_parameter(user_id, request, answer)
        check_corr_function(user_id, request, answer)
        check_corr_parameter(user_id, request, answer)

        if 'refresh' in request.form:
            load_data(answer)

        if 'save' in request.form:
            save(user_id, answer)
    else:  # первый вывод формы
        cd.write_log('Параметры сервисов', user_id, request)
        load_data(answer)

    if not answer['functions'] or answer['functions'][0]['id'] != 0:
        answer['functions'].insert(0, {'id': 0, 'sh_name': ''})
    answer['ajax_form'] = True
    cd.save_form(user_id, array_default, answer, 'function_')
    return answer
