import json
import os
import time
import datetime
import platform
import zoneinfo

from flask import session
from flask import flash
import requests
from requests.exceptions import HTTPError

import users_session
import config
import colors
from ohi_shared.text_utils import decode, encode, str1000, get_duration  # noqa: F401

version = 'version 1.4.0 - 09.09.2026'  # версия программы вэб сайта
app_lang = 'ru'
current_path = ''


def exist(user_id):
    return users_session.users.exist(user_id)


def add(user_id, key, value):
    users_session.users.add(user_id, key, value)


def get(user_id, key):
    return users_session.users.get(user_id, key)


def default(user_id, key, value):
    users_session.users.default(user_id, key, value)


def clear(user_id):
    return users_session.users.clear(user_id)


def to_string():
    return users_session.users.to_string()


def find_user(user_id, req):
    return users_session.users.find_user(user_id, req)


def login_admin():
    result = False
    token_admin = ''
    lang_admin = ''
    txt_z = {"login": "superadmin", "password": decode('abcd', config.kirill), "rememberMe": True}
    try:
        headers = {"Accept": "application/json"}
        response = requests.request(
            'POST', config.URL + 'v1/login', headers=headers,
            json={"params": txt_z}
            )
    except HTTPError as err:
        txt = f'HTTP error occurred: {err}'
    except Exception as err:
        txt = f'Other error occurred: : {err}'
    else:
        try:
            txt = response.text
            result = response.ok
            if result:
                js = json.loads(txt)
                if "accessToken" in js:
                    token_admin = js["accessToken"]
                    token_admin = decode(decode('abcd', config.kirill), token_admin)
                    token_admin = json.loads(token_admin)
                if 'lang' in js:
                    lang_admin = js['lang']
            else:
                token = None
                return txt, result, token
        except Exception as err:
            txt = f'Error occurred: : {err}'
    return txt, result, token_admin, lang_admin


def send_rest(mes, directive="GET", params=None, lang='', token_user=None):
    js = {}
    if token_user is not None:
        # js['token'] = token_user
        js['token'] = encode(decode('abcd', config.kirill), json.dumps(token_user))
    if lang == '':
        lang = app_lang
    if directive == 'GET' and 'lang=' not in mes:
        if '?' in mes:
            mes = mes + '&lang=' + lang
        else:
            mes = mes + '?lang=' + lang
    else:
        js['lang'] = lang   # код языка пользователя
    if params:
        if type(params) is not str:
            params = json.dumps(params, ensure_ascii=False)
        js['params'] = params  # дополнительно заданные параметры
    try:
        headers = {"Accept": "application/json"}
        response = requests.request(directive, config.URL + mes.replace(' ', '+'), headers=headers, json=js)
    except HTTPError as err:
        txt = f'HTTP error occurred: {err}'
        return txt, False, None
    except Exception as err:
        txt = f'Other error occurred: {err}'
        return txt, False, None
    else:
        return response.text, response.ok, '<' + str(response.status_code) + '> - ' + response.reason


def write_log_db(level, src, msg, page=None, file_name='', law_id='', td=None):
    if page is None or page == '':
        page = 'NULL'
    if law_id is None:
        law_id = ''
    if file_name is None:
        file_name = ''
    comment = msg
    td = 'NULL' if td is None else "%.1f" % td if type(td) == float else td
    st = "insert into {schema}.logs (level, source, comment, page, law_id, file_name, td) values " \
         "('{level}', '{source}', %s, {page}, '{law_id}', %s, {td})".format(
            schema=config.SCHEMA, level=level, source=src,  page=page, law_id=law_id, td=td)
    txt, ok, token, lang = login_admin()
    if ok:
        datas = (comment, file_name)
        answer, ok, status = send_rest(
            'v2/execute?need_answer=0', 'PUT', params={"script": st, "datas": datas}, lang=lang, token_user=token)
        if not ok:
            flash(str(answer), 'warning')


def st_system(request):
    try:
        return request.headers.environ['HTTP_SEC_CH_UA_PLATFORM']
    except Exception as err:
        return f"{err}"


def st_address(request):
    """
    Retrieves the remote address (IP address) from the request object.

    Args:
        request (flask.Request): The request object containing the client's request data.

    Returns:
        str: The remote address (IP address) of the client.
    """
    # dict.get(key, default) вычисляет default всегда, даже когда key уже
    # присутствует - request.environ['REMOTE_ADDR'] дёргался безусловно и
    # падал с KeyError, если этого ключа в окружении вдруг не было (даже при
    # наличии HTTP_X_FORWARDED_FOR). request.remote_addr - штатное свойство
    # Flask/Werkzeug, само не кидает исключений (возвращает None, если адрес
    # не удалось определить).
    try:
        return request.environ.get('HTTP_X_FORWARDED_FOR') or request.remote_addr or ''
    except Exception as err:
        print(str(err))
        return ''


def ip_good(request):
    # ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
    ip = st_address(request)
    if ip != '127.0.0.1':
        return ip


def login(e_mail, password, ip_address):
    result = False
    txt_z = {"login": e_mail, "password": password, "rememberMe": True, "category": config.SCHEMA}
    try:
        headers = {"Accept": "application/json"}
        response = requests.request(
            'POST', config.URL + 'v1/login', headers=headers,
            json={"params": txt_z}
            )
    except HTTPError as err:
        txt = f'HTTP error occurred: {err}'
    except Exception as err:
        txt = f'Other error occurred: : {err}'
    else:
        try:
            txt = response.text
            result = response.ok
            if result:
                js = json.loads(txt)
                token_db = ''
                if "accessToken" in js:
                    token_db = js["accessToken"]

                token = decode(decode('abcd', config.kirill), token_db)
                token = json.loads(token)
                rights = 'visible'
                users_session.users.load()
                for key in token.keys():
                    if key == '***':
                        rights = 'visible, admin'
                    elif token[key] != 'GET' and token[key] != '' and 'visible' in token[key]:
                        rights = token[key]
                        break
                user_id = users_session.users.id_by_name(ip_address)
                if user_id is None:
                    user_id = os.urandom(20).hex()
                    users_session.users.add_user(user_id)
                users_session.users.clear(user_id)
                users_session.users.add(user_id, "user_name", e_mail)
                users_session.users.add(user_id, "token", token_db)
                users_session.users.add(user_id, "rights", rights)

                if "expires" in js:
                    users_session.users.add(user_id, "expires", time.mktime(
                        time.strptime(js["expires"], '%Y-%m-%d %H:%M:%S')))
                if 'lang' in js:
                    users_session.users.add(user_id, "app_lang", js['lang'])
                if 'role' in js:
                    users_session.users.add(user_id, "user_role", js['role'])
                answer, ok, token_admin, lang_admin = login_admin()
                if ok:
                    add(user_id, 'token', token_admin)
                    add(user_id, 'lang', lang_admin)

                users_session.users.save()
                return txt, result, user_id
            else:
                return txt, result, ''
        except Exception as err:
            txt = f'Error occurred: : {err}'
    return txt, result, ''


def make_login(user_name, password, ip_address):
    try:
        txt, result, user_id = login(user_name, password, ip_address)
        if not result:
            try:
                txt = json.loads(txt)
                flash('Error login : ' + txt['detail'] + '; user_name=' + user_name, 'warning')
            except Exception as er:
                flash('Error login : ' + txt + '; user_name=' + user_name + ': ' + f"{er}", 'warning')
        return result, user_id
    except Exception as er:
        print('ERROR', 'make_login', f"{er}")
        return False, ''


def get_guest(user_id, ip_text):
    if ip_text != '127.0.0.1':
        answer, ok, status_result = send_rest("v1/content/{schema}/guests?where=sh_name='{ip}'".format(
            schema=config.SCHEMA, ip=ip_text))
        if ok:
            answer = json.loads(answer)
            if len(answer) == 0:  # записать нового пользователя
                country = get(user_id, 'country')
                city = get(user_id, 'city')
                txt = "null, '" + ip_text + "', '" + country + "', '" + city + "'"
                answer, ok, status_result = send_rest('v1/object/{schema}/guests?param_list={param_list}'.format(
                    schema=config.SCHEMA, param_list=txt), 'PUT', token_user=get(user_id, 'token'))
                if not ok:
                    print('get_quest', str(answer))


def define_guest(ip_text):
    """
    Determines the country and city of a guest based on their IP address.

    Args:
        ip_text (str): The IP address of the guest.

    Returns:
        tuple: A tuple containing the country, city, and a boolean indicating success.
               If the IP address is '127.0.0.1', returns ('', '', True).
               If an error occurs, returns the error message, '', and False.
    """
    if ip_text == '127.0.0.1':
        return '', '', True

    headers = {"Accept": "application/json"}
    try:
        response = requests.get(f'http://ip-api.com/json/{ip_text}?lang=ru', headers=headers)
        response.raise_for_status()
    except HTTPError as err:
        print('ERROR', 'Ошибка запроса', f'HTTP error occurred: {err}')
        return f'HTTP error occurred: {err}', '', False
    except Exception as err:
        return f'{err}', '', False

    try:
        answer = response.json()
        if response.ok and 'country' in answer:
            return answer['country'], answer['city'], True
        return response.text.replace('\\n', '\n'), '', False
    except Exception as err:
        return f'{err}', '', False


def get_timezone_minutes_by_ip(ip_text):
    """Определяет часовой пояс гостя по IP (для входов в обход обычной формы
    логина, где часовой пояс присылает браузер - см. user_from_chat) - в
    минутах смещения от UTC, как time_zone везде в проекте. ip-api.com (тот
    же сервис, что и define_guest) в ответе уже отдаёт IANA-имя пояса
    (например "Europe/Moscow"), из него через zoneinfo считаем офсет с
    учётом текущего перехода на летнее/зимнее время. None, если определить
    не удалось (127.0.0.1, сеть недоступна, неизвестный IP и т.п.) - тогда
    вызывающий код сам решает, какое значение подставить по умолчанию.
    """
    if ip_text == '127.0.0.1':
        return None
    try:
        response = requests.get(f'http://ip-api.com/json/{ip_text}', headers={"Accept": "application/json"},
                                timeout=3)
        response.raise_for_status()
        answer = response.json()
        tz_name = answer.get('timezone') if response.ok else None
        if not tz_name:
            return None
        offset = datetime.datetime.now(zoneinfo.ZoneInfo(tz_name)).utcoffset()
        return int(offset.total_seconds() // 60)
    except Exception:
        return None


def fix_login(ip, value):
    if ip.strip() == '127.0.0.1':
        return
    # фиксация логина (текст в value) пользователя
    answer, ok, status_result = send_rest("v1/content/{schema}/guests?where=sh_name='{ip}'".format(
        schema=config.SCHEMA, ip=ip))
    if ok:
        answer = json.loads(answer)
        if len(answer) != 0:  # есть пользователь
            guest_id = answer[0]['id']
            url = "v1/MDM/his/{schema}/guests/{param}/{obj_id}?value='{value}'".format(
                schema=config.SCHEMA, param='page', obj_id=guest_id, value=value)
            answer, ok, token_admin, lang_admin = login_admin()
            answer, ok, status_result = send_rest(url, 'POST', token_user=token_admin)
            if not ok:
                print('write_quest', str(answer))


def init_form(user_id, request, endpoint):
    users_session.users.load()
    user_id = find_user(user_id, request)
    if not exist(user_id):
        session['page_for_return'] = endpoint
        users_session.users.save()
        return '/login/'
    return None


def write_quest(user_id, request, name_page):
    # txt = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
    country = ''
    city = ''
    txt = st_address(request)
    if txt == '127.0.0.1':
        return country, city
    guest_id = None
    answer, ok, status_result = send_rest("v1/content/{schema}/guests?where=sh_name='{ip}'".format(
        schema=config.SCHEMA, ip=txt))
    if ok:
        answer = json.loads(answer)
        if len(answer) == 0:  # записать нового пользователя
            country, city, ok_ip = define_guest(txt)
            if not ok_ip:
                country = city = ''
            txt = "null, '" + txt + "', '" + country + "', '" + city + "'"
            answer, ok, status_result = send_rest('v1/object/{schema}/guests?param_list={param_list}'.format(
                schema=config.SCHEMA, param_list=txt), 'PUT', token_user=get(user_id, 'token'))
            if not ok:
                print('write_quest', str(answer))
            else:
                guest_id = int(answer.replace('"', ''))
        else:
            guest_id = answer[0]['id']
            country = answer[0]['country']
            city = answer[0]['city']
            if country is None or country == '' or city is None or city == '':
                country, city, ok_ip = define_guest(txt)
                txt = str(guest_id) + ", '" + txt + "', '" + country + "', '" + city + "'"
                send_rest('v1/object/{schema}/guests?param_list={param_list}'.format(
                    schema=config.SCHEMA, param_list=txt), 'PUT', token_user=get(user_id, 'token'))
        if guest_id is not None:
            url = "v1/MDM/his/{schema}/guests/{param}/{obj_id}?value='{value}'".format(
                schema=config.SCHEMA, param='page', obj_id=guest_id, value=name_page)
            answer, ok, status_result = send_rest(url, 'POST', token_user=get(user_id, 'token'))
            if not ok:
                print('write_quest', str(answer))
    else:
        print('write_quest', str(answer))
    return country, city


def write_log(source, user_id, request, law_id='', page=None, mes='Вход пользователя на страницу'):
    ip = ip_good(request)
    if ip:
        write_quest(user_id, request, source)
        create_user_address(user_id, request)
        write_log_db('USER', source, mes, law_id=law_id, page=page, file_name=get(user_id, 'user_address'))


def default_form(user_id, array, answer, prefix):
    for data in array:
        default(user_id, prefix + data['key'], data['value'])
        answer[data['key']] = get(user_id, prefix + data['key'])


def save_form(user_id, array, answer, prefix):
    for data in array:
        add(user_id, prefix + data['key'], answer[data['key']])


def define_param_for_page(request, answer):
    if 'row_count' not in answer:
        return
    last_row_count = int(request.form.get('row_count', 5))
    answer['change_page'] = False
    answer['change_sort'] = False
    answer['change_search'] = False
    if 'scroll' in request.form and request.form.get('scroll'):
        answer['scroll'] = float(request.form.get('scroll'))
    if 'page' in request.form:
        answer['change_page'] = answer['page'] != int(request.form.get('page'))
        answer['page'] = int(request.form.get('page'))
    if 'row_count' in request.form:
        answer['row_count'] = int(request.form.get('row_count'))

    if last_row_count != int(request.form.get('row_count', 5)):  # сменилось количество строк в таблице
        # answer['page'] = last_page * last_row_count // answer['row_count'] + 1
        # if not answer['change_page']:
        answer['page'] = 1
        answer['scroll'] = 0
        answer['change_page'] = True

    if 'next' in request.form:
        answer['page'] = answer['page'] + 1
        answer['change_page'] = True
        answer['scroll'] = 0
    if 'prev' in request.form:
        answer['page'] = answer['page'] - 1
        answer['change_page'] = True
        answer['scroll'] = 0
    if 'search' in request.form:
        if answer['search'] != request.form.get('search'):
            answer['change_search'] = True
        answer['search'] = request.form.get('search')
    for key in request.form.keys():
        if 'page(' in key:
            st2, st2 = key.split('page(')
            if st2 != '...)':
                answer['page'] = int(st2.split(')')[0])
                answer['scroll'] = 0
                answer['change_page'] = True
            break
    if 'sort' in request.form:
        if answer['selected_sort'] != request.form.get('sort'):
            answer['change_sort'] = True
            answer['change_page'] = True
        answer['selected_sort'] = request.form.get('sort')
        # answer['page'] = 1
    if 'sort_trend0' in request.form:
        if answer['sort_trend'] != 0:
            answer['change_sort'] = True
            answer['change_page'] = True
        answer['sort_trend'] = 0
        # answer['page'] = 1
    if 'sort_trend1' in request.form:
        if answer['sort_trend'] != 1:
            answer['change_sort'] = True
            answer['change_page'] = True
        answer['sort_trend'] = 1


def define_pages(answer):
    count = answer['count'] if 'count' in answer else None
    answer['count'] = 0 if count is None else count
    answer['page_count'] = (answer['count'] + int(answer['row_count']) - 1) // int(answer['row_count'])
    answer['page'] = max(1, answer['page'])
    answer['page'] = min(answer['page'], max(1, answer['page_count']))
    answer['page'] = min(answer['page'], (answer['count'] + answer['row_count'] - 1) // answer['row_count'])
    answer['array_pages'] = define_button(answer['page_count'], answer['page'])
    answer['first'] = str((answer['page'] - 1) * int(answer['row_count']) + 1) if answer['count'] != 0 else '0'
    last = answer['page'] * int(answer['row_count']) if answer['count'] != 0 else 0
    answer['last'] = str(min(last, answer['count']))


def define_button(last_page, page_from):
    array_pages = list()
    length = 5
    for i in range(length):
        array_pages.append({})
    try:
        q = last_page - 2
        if q < 5:
            for i in range(length):
                if i < q:
                    array_pages[i]['visible'] = True
                    array_pages[i]['page'] = i + 2
                    array_pages[i]['text'] = 'page(' + str(i+2) + ')'
                else:
                    array_pages[i]['visible'] = False
        else:
            array_pages[0]['text'] = '...'
            array_pages[-1]['text'] = '...'
            if page_from <= 4:
                pages = ['2', '3', '4', '5', '...']
            else:
                if page_from > last_page - 4:
                    pages = ['...', str(last_page - 4), str(last_page - 3), str(last_page - 2), str(last_page - 1)]
                else:
                    pages = ['...', str(page_from - 1), str(page_from), str(page_from + 1), '...']
            for i in range(length):
                array_pages[i]['visible'] = True
                array_pages[i]['text'] = 'page(' + pages[i] + ')'
                if pages[i] == '...':
                    array_pages[i]['page'] = pages[i]
                else:
                    array_pages[i]['page'] = int(pages[i])
        if last_page > 1:
            array_pages.append({'visible': True, "page": last_page, "text": "page(" + str(last_page) + ")"})
    except Exception as er:
        print('table', 'define_button', f"{er}")
    return array_pages


def get_where(search, columns):
    where = ''
    if search:
        array_search = search.split('&')
        for unit in array_search:
            list_search = unit.split(';')
            where_or = ''
            for search in list_search:
                where_or = where_or + ' or ' if where_or != '' else where_or
                st_column = ''
                for column in columns:
                    st_column = st_column + ' or ' if st_column != '' else st_column
                    st_column += (column + " ilike N'%{search}%'")
                where_or = where_or + "(" + st_column.format(search=search.strip()) + ")"
            if where_or != '':
                where = where + ' and ' if where != '' else where
            where += '(' + where_or + ')'
    return where


def get_date_sql(st, time_zone):
    if type(st) == list:
        year = st[0]
        month = st[1]
        day = st[2]
    else:
        year, month, day = st.split('-')
    date = datetime.datetime(int(year), int(month), int(day))
    dt = date + datetime.timedelta(minutes=time_zone if time_zone else 0)
    return '{year}-{month}-{day} {hour}:{minute}:{second}'.format(
        year=dt.year, month=dt.month, day=dt.day, hour=dt.hour, minute=dt.minute, second=dt.second)


def st_today():
   return datetime.datetime.now().strftime('%Y-%m-%d')

def translate_from_base(st):
    if st is None:
        return ''
    st = st.replace('~A~', '(').replace('~B~', ')').replace('~a1~', '@').replace('~LF~', '\n')
    st = st.replace('~a2~', ',').replace('~a3~', '=').replace('~a4~', '"').replace('~a5~', "'")
    st = st.replace('~a6~', ':').replace('~b1~', '/').replace('~b2~', '&').replace('~R~', '\r')
    return st


def get_st_date(year, month, day):
    return str(year) + '-' + str(month).rjust(2, '0') + '-' + str(day).rjust(2, '0')


def calc_day(year, month, day, delta):
    dt = datetime.date(int(year), int(month), int(day)) + datetime.timedelta(days=delta)
    return dt.year, dt.month, dt.day


def user_from_chat(request, new_id=None):
    ok, user_id = make_login('llm', 'llm', st_address(request))
    if not ok:
        return False, ''
    users_session.users.load()
    create_user_address(user_id, request)
    add(user_id, 'theme', 'black')
    # В отличие от обычного логина (login.py читает часовой пояс из браузера
    # через time_now/GMT), у входа из чат-бота нет браузерной формы, чтобы
    # его узнать - без значения по умолчанию get(user_id, 'time_zone')
    # оставался бы None, и унарный минус над ним валил бы 500-й ошибкой
    # любую страницу с разбивкой по суткам (news_board, chat_logs, logs).
    # Пытаемся определить точнее по IP (geo -> IANA-пояс -> офсет в минутах),
    # и только если не вышло - берём разумное значение по умолчанию (Москва).
    if get(user_id, 'time_zone') is None:
        add(user_id, 'time_zone', get_timezone_minutes_by_ip(st_address(request)) or 180)

    upr = {
        'user_name': get(user_id, 'user_name'),
        'user_id': user_id,
        'schema': config.SCHEMA,
        'admin': 'admin' in get(user_id, 'rights'),
        'theme': 'black',
        'select_theme': 'black',
        'colors': colors.colors['black'],
        'time_zone': get(user_id, 'time_zone'),
        'select_language': 'ru'
    }
    add(user_id, 'upr', upr)
    users_session.users.save()

    if not ok:
        return False, user_id
    if not exist(user_id) or 'visible' not in get(user_id, 'rights'):
        flash('Для пользователя {user_name} нет доступа к базе данных'.format(
            user_name=get(user_id, 'user_name')))
        return False

    write_log_db('USER', 'Nasha_stengazeta', 'Вход пользователя на WEB сайт из Nasha_stengazeta ' +
                 st_system(request) + ' [' + request.environ.get('HTTP_USER_AGENT') + ']',
                 file_name=get(user_id, 'user_address'), page=new_id,
                 law_id=request.form.get('user_name'))
    # записать пользователя в список пользователей
    get_guest(user_id, st_address(request))

    # зафиксировать лог пользователя
    fix_login(st_address(request), 'Login из Nasha_stengazeta ({user_name})'.format(
        user_name=get(user_id, 'user_name')))
    return True, user_id


def choose_language(user_id, request):
    if 'select_language' in request.form:
        upr = get(user_id, 'upr')
        upr['select_language'] = request.form.get('select_language')
        add(user_id, 'upr', upr)
    if 'select_theme_form' in request.form:
        add(user_id, 'theme', request.form.get('select_theme_form'))
        upr = get(user_id, 'upr')
        upr['select_theme'] = request.form.get('select_theme_form')
        upr['colors'] = colors.colors[get(user_id, 'theme')]
        add(user_id, 'upr', upr)


def create_user_address(user_id, request):
    """
    Creates and stores the user's address information.

    Args:
        user_id (str): The unique identifier of the user.
        request (flask.Request): The request object containing the user's request data.

    This function performs the following steps:
    1. Defines the guest's country and city based on the IP address from the request.
    2. If the IP address is not valid, sets the country and city to empty strings.
    3. Constructs the user address string using the user's name, IP address, system information, country, and city.
    4. Adds the user address, country, and city to the user's session data.
    """
    country, city, is_ok = define_guest(st_address(request))
    if not is_ok:
        country = city = ''
    user_address = f"user={get(user_id, 'user_name')}; {st_address(request)}; system={st_system(request)} {country} {city}"
    add(user_id, 'user_address', user_address)
    add(user_id, 'country', country)
    add(user_id, 'city', city)


def define_st(txt):
    return txt if txt else ''


def calc_st_month(year, month, day, delta):
    year = int(year)
    month = int(month)
    month += delta
    while month <= 0:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return '{year}-{month}-{day}'.format(year=str(year).zfill(3), month=str(month).zfill(2), day=str(day).zfill(2))


def get_inform_about_os():
    os_name = platform.system()
    os_release = platform.release()
    os_version = platform.version()
    os_info = platform.platform()
    architecture = platform.architecture()
    processor = platform.processor()
    return f'{os_name}; {os_release}; {os_version};\n{os_info};\n{architecture};\n{processor}'


def days_phrase(days):
    days = int(days)
    if 11 <= days % 100 <= 14:
        suffix = 'дней'
    else:
        last = days % 10
        if last == 1:
            suffix = 'день'
        elif 2 <= last <= 4:
            suffix = 'дня'
        else:
            suffix = 'дней'
    return f"{days} {suffix}"


def convert_time_to_timezone(datetime_utc_str, time_zone_minutes, only_time=False, format=None):
    """
    Преобразует строку даты и времени UTC с учетом заданного смещения часового пояса.

    Args:
        datetime_utc_str (str): Строка даты и времени в UTC формате.
        time_zone_minutes (int): Смещение часового пояса в минутах.

    Returns:
        str: Строка даты и времени с учетом часового пояса в том же формате.
    """
    try:
        # Определяем формат входной строки
        if 'T' in datetime_utc_str:
            if '.' in datetime_utc_str:
                dt_format = "%Y-%m-%dT%H:%M:%S.%f"
            else:
                dt_format = "%Y-%m-%dT%H:%M:%S"
        else:
            if '.' in datetime_utc_str:
                dt_format = "%Y-%m-%d %H:%M:%S.%f"
            else:
                dt_format = "%Y-%m-%d %H:%M:%S"

        # Преобразуем строку в datetime объект
        dt_utc = datetime.datetime.strptime(datetime_utc_str, dt_format)

        # Применяем смещение
        dt_local = dt_utc + datetime.timedelta(minutes=time_zone_minutes)

        if format is None:
            format = dt_format
        # Используем заданный или исходный формат (но без Т)
        return dt_local.strftime(format).replace('T', ' ')
    except Exception as e:
        return f"Ошибка преобразования времени: {str(e)}"


def what_change(unit, current, keys=None):
    """
    Сравнивает два объекта (unit — исходное состояние, current — текущее) и возвращает
    JSON-строку с описанием различий. Поддерживает вложенные словари и списки.

    :param unit:    Исходное значение (dict, list или скаляр)
    :param current: текущее значение (dict, list или скаляр)
    :param keys:    Список ключей для отслеживания (только для dict); если None — все ключи
    :return:        JSON-строка с описанием изменений (пустой объект «{}» если изменений нет)
    """
    if keys is not None and isinstance(unit, dict) and isinstance(current, dict):
        unit = {k: unit[k] for k in keys if k in unit}
        current = {k: current[k] for k in keys if k in current}

    def _diff(old, new):
        """Рекурсивно вычисляет разницу между old и new."""

        # Оба значения — словари: сравниваем поключево
        if isinstance(old, dict) and isinstance(new, dict):
            changes = {}
            all_keys = set(old) | set(new)
            for key in sorted(all_keys):
                if key not in new:
                    # ключ удалён
                    changes[key] = {'old': old[key], 'new': None}
                elif key not in old:
                    # ключ добавлен
                    changes[key] = {'old': None, 'new': new[key]}
                else:
                    nested = _diff(old[key], new[key])
                    if nested is not None:
                        changes[key] = nested
            return changes if changes else None

        # Оба значения — списки: сравниваем поэлементно
        if isinstance(old, list) and isinstance(new, list):
            if old == new:
                return None
            changes = {}
            max_len = max(len(old), len(new))
            for i in range(max_len):
                if i >= len(old):
                    changes[f'[{i}]'] = {'old': None, 'new': new[i]}
                elif i >= len(new):
                    changes[f'[{i}]'] = {'old': old[i], 'new': None}
                else:
                    nested = _diff(old[i], new[i])
                    if nested is not None:
                        changes[f'[{i}]'] = nested
            return changes if changes else None

        # Скалярные значения (или разнотипные объекты)
        if old != new:
            return {'old': old, 'new': new}
        return None

    if not isinstance(unit, (dict, list)) or not isinstance(current, (dict, list)):
        # Если хотя бы один аргумент не dict/list — сравниваем как скаляры
        result = _diff(unit, current)
        return json.dumps(result if result else {}, indent=4, ensure_ascii=False)

    result = _diff(unit, current)
    if result:
        return json.dumps(result, indent=4, ensure_ascii=False)
    else:
        return ''
