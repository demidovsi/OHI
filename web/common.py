import copy

from flask import session, has_request_context
from flask import flash
from typing import Optional, Union
import json
import os
import re
import threading
import time
import datetime
import platform
import zoneinfo

import requests
from requests.exceptions import HTTPError

import config
import colors
from ohi_shared.text_utils import decode, encode, str1000, get_duration  # noqa: F401
from shared_web import visits  # учёт посетителей — общий для сайтов (копия parlaments/shared_web)

version = 'version 2.0.0 - 20.10.2026'  # версия программы вэб сайта
app_lang = 'ru'
current_path = ''


# ── Сессия пользователя ─────────────────────────────────────────────────────────
# Как в сайтах parlaments (sozd-web, kns-web): user_id в адресах и users_session.py больше нет. Кто вошёл — в
# подписанной cookie Flask (session, SECRET_KEY из FLASK_SECRET_KEY): случайный ключ сессии 'sid' и «паспорт»
# ('ident' — имя, права, роль, язык, тема, ...). Состояние форм (фильтры, страницы, сортировки) — в памяти процесса
# (_STATE[sid]). Если запрос попал на другой экземпляр Cloud Run (или процесс перезапустился), состояние
# восстанавливается из паспорта: пользователь остаётся залогинен, фильтры форм — по умолчанию.
# Токен superadmin в cookie не хранится — берётся заново.

# ключи «паспорта» — переживают смену экземпляра; upr — без colors (цвета по теме)
IDENTITY_KEYS = ('user_name', 'rights', 'user_role', 'app_lang', 'expires', 'ip', 'country', 'city', 'os',
                 'browser', 'user_info', 'time_zone', 'theme', 'schema', 'guest_id', 'upr')
_STATE = {}                   # sid -> состояние сессии
_STATE_LOCK = threading.Lock()
_STATE_TTL = 24 * 3600        # состояние, к которому не обращались сутки, удаляется (как и cookie)


def _sid(create=False):
    """Ключ сессии текущего запроса (из cookie); create — создать новую сессию, если её нет."""
    if not has_request_context():
        return None
    sid = session.get('sid')
    if not sid and create:
        sid = os.urandom(20).hex()
        session['sid'] = sid
        session.permanent = True
    return sid


def _restore(ident):
    """Состояние сессии из «паспорта» cookie (другой экземпляр / перезапуск процесса)."""
    st = dict(ident or {})
    upr = st.get('upr')
    if isinstance(upr, dict):
        upr = dict(upr)
        upr['colors'] = colors.colors.get(upr.get('theme') or st.get('theme') or 'white', colors.colors['white'])
        st['upr'] = upr
    if st.get('rights') is not None:
        _, ok, token_admin, _ = login_admin()
        if ok:
            st['token'] = token_admin
    return st


def _state(create=False):
    sid = _sid(create)
    if not sid:
        return None
    now = time.time()
    with _STATE_LOCK:
        st = _STATE.get(sid)
        if st is None and (create or session.get('ident')):
            st = _restore(session.get('ident'))
            _STATE[sid] = st
            for key in [k for k, v in _STATE.items() if now - v.get('_ts', now) > _STATE_TTL]:
                _STATE.pop(key, None)
        if st is not None:
            st['_ts'] = now
    return st


def _save_identity(st):
    ident = {k: st[k] for k in IDENTITY_KEYS if k in st}
    if isinstance(ident.get('upr'), dict):
        ident['upr'] = {k: v for k, v in ident['upr'].items() if k != 'colors'}
    session['ident'] = ident


def new_session():
    """Новая сессия (вход пользователя): прежнее состояние браузера сбрасывается."""
    old = session.get('sid') if has_request_context() else None
    if old:
        with _STATE_LOCK:
            _STATE.pop(old, None)
    session.clear()
    _sid(create=True)
    with _STATE_LOCK:
        _STATE[session['sid']] = {'_ts': time.time()}


def end_session():
    """Выход: состояние и cookie сессии удаляются."""
    old = session.get('sid') if has_request_context() else None
    if old:
        with _STATE_LOCK:
            _STATE.pop(old, None)
    if has_request_context():
        session.clear()


def add(key, value):
    st = _state(create=True)
    if st is None:
        return
    st[key] = value
    if key in IDENTITY_KEYS:
        _save_identity(st)


def get(key):
    st = _state()
    return st.get(key) if st else None


def default(key, value):
    # копия: значения по умолчанию (array_default форм) — общие объекты модуля; правка состояния одной сессии
    # (unit, списки) не должна попадать в другие (раньше сессии сериализовались в файл, и общих объектов не было)
    st = _state(create=True)
    if st is not None and key not in st:
        add(key, copy.deepcopy(value))


def exist():
    """Пользователь вошёл (есть права)."""
    st = _state()
    return bool(st) and st.get('rights') is not None


def is_admin():
    return exist() and 'admin' in (get('rights') or '')


# ── REST API бэкенда ───────────────────────────────────────────────────────────

_admin_cache = {'until': 0.0, 'value': None}
_ADMIN_TTL = 3600  # токен superadmin кэшируется на час (раньше — вход на каждую запись в журнал)


def login_admin():
    """Вход superadmin. Возвращает (текст, is_ok, токен_dict, язык); токен кэшируется на _ADMIN_TTL секунд."""
    now = time.time()
    if _admin_cache['value'] is not None and now < _admin_cache['until']:
        return _admin_cache['value']
    result = False
    token_admin = ''
    lang_admin = ''
    txt_z = {"login": "superadmin", "password": decode('abcd', config.kirill), "rememberMe": True}
    try:
        headers = {"Accept": "application/json"}
        response = requests.request('POST', config.URL + 'v1/login', headers=headers, json={"params": txt_z})
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
                    token_admin = json.loads(decode(decode('abcd', config.kirill), js["accessToken"]))
                if 'lang' in js:
                    lang_admin = js['lang']
        except Exception as err:
            txt = f'Error occurred: : {err}'
            result = False
    value = (txt, result, token_admin, lang_admin)
    if result:
        _admin_cache['value'] = value
        _admin_cache['until'] = now + _ADMIN_TTL
    return value


def send_rest(mes, directive="GET", params=None, lang='', token_user=None):
    js = {}
    if token_user is not None:
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


def write_log_db(
    level: str,
    src: str,
    msg: str,
    page: Optional[Union[int, str]] = None,
    file_name: str = '',
    law_id: str = ' ',
    td: Optional[float] = None,
) -> None:
    """Запись в журнал {schema}.logs. Пустой file_name в запросе вошедшего пользователя заменяется на его user_info
    (IP, страна, город, ОС, браузер)."""
    answer, is_ok, token, lang = login_admin()
    if not is_ok:
        print(f"{time.ctime()} ERROR write_log_db: {answer}", flush=True)
        return
    if page is None or page == '':
        page = 'NULL'
    if law_id is None:
        law_id = ''
    if not file_name:
        file_name = ''
    if not file_name and has_request_context() and exist():
        file_name = get('user_info') or ''
    td = 'NULL' if td is None else "%.1f" % td if type(td) == float else td
    if page != 'NULL':
        page = int(page)
    # level, source, comment, law_id, file_name — параметрами (%s), а не в тексте SQL
    st = "insert into {schema}.logs (level, source, comment, page, law_id, file_name, td) values " \
         "(%s, %s, %s, {page}, %s, %s, {td})".format(schema=config.SCHEMA, page=page, td=td)
    datas = (level, src, msg, str(law_id), file_name)
    answer, ok, status = send_rest(
        'v2/execute?need_answer=0', 'PUT', params={"script": st, "datas": datas}, lang=lang, token_user=token)
    if not ok:
        print(f"{time.ctime()} ERROR write_log_db: {answer}", flush=True)
        if has_request_context():
            flash(str(answer), 'warning')


# ── Клиент ─────────────────────────────────────────────────────────────────────

def st_system(request):
    try:
        return request.headers.environ['HTTP_SEC_CH_UA_PLATFORM']
    except Exception as err:
        return f"{err}"


def st_address(request):
    """IP клиента: первый адрес X-Forwarded-For (дальше — прокси), иначе адрес соединения (shared_web/visits.py)."""
    try:
        return visits.client_ip(request)
    except Exception as err:
        return f"{err}"


def ip_good(request):
    ip = st_address(request)
    if not visits.is_local(ip):
        return ip


def get_client_info(request) -> dict:
    """Информация о клиенте: 'ip', 'country', 'city', 'os', 'browser'."""
    ip = visits.client_ip(request)
    country, city = visits.geo(ip)  # геолокация по IP (с кэшем; локальный адрес — пусто)

    os_name = request.headers.get('Sec-CH-UA-Platform', '').strip('"')
    ua = request.headers.get('User-Agent', '')
    if not os_name:
        if 'Android' in ua:
            os_name = 'Android'
        elif 'iPhone' in ua or 'iPad' in ua:
            os_name = 'iOS'
        elif 'Windows NT' in ua:
            os_name = 'Windows'
        elif 'Mac OS X' in ua:
            os_name = 'macOS'
        elif 'Linux' in ua:
            os_name = 'Linux'

    browser = ''
    if 'OPR/' in ua or 'Opera' in ua:
        browser = 'Opera'
    elif 'Edg/' in ua:
        browser = 'Edge'
    elif 'YaBrowser/' in ua:
        browser = 'Yandex Browser'
    elif 'Chromium/' in ua:
        browser = 'Chromium'
    elif 'Chrome/' in ua:
        browser = 'Chrome'
    elif 'Firefox/' in ua:
        browser = 'Firefox'
    elif 'Safari/' in ua:
        browser = 'Safari'
    elif 'MSIE' in ua or 'Trident/' in ua:
        browser = 'Internet Explorer'

    return {'ip': ip, 'country': country, 'city': city, 'os': os_name, 'browser': browser}


def remember_client(request):
    """Данные клиента — в сессию (ip, country, city, os, browser, user_info для журнала)."""
    info = get_client_info(request)
    for key in ('ip', 'country', 'city', 'os', 'browser'):
        add(key, info[key])
    add('user_info', '; '.join([info['ip'], info['country'], info['city'], info['os'], info['browser']]))
    return info


def get_timezone_hours_by_ip(ip_text):
    """Часовой пояс гостя по IP (для входа из чат-бота, где браузер не присылает время) — смещение от UTC в часах;
    None, если определить не удалось."""
    if visits.is_local(ip_text):
        return None
    try:
        response = requests.get(f'http://ip-api.com/json/{ip_text}', headers={"Accept": "application/json"},
                                timeout=3)
        response.raise_for_status()
        tz_name = response.json().get('timezone')
        if not tz_name:
            return None
        offset = datetime.datetime.now(zoneinfo.ZoneInfo(tz_name)).utcoffset()
        return int(offset.total_seconds() // 3600)
    except Exception:
        return None


# ── Вход пользователя ──────────────────────────────────────────────────────────

def login(e_mail, password):
    """Вход пользователя через v1/login бэкенда: новая сессия, права, роль; запросы к бэкенду — с токеном superadmin."""
    result = False
    txt_z = {"login": e_mail, "password": password, "rememberMe": True, "category": config.SCHEMA}
    try:
        headers = {"Accept": "application/json"}
        response = requests.request('POST', config.URL + 'v1/login', headers=headers, json={"params": txt_z})
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
                token = json.loads(decode(decode('abcd', config.kirill), js.get("accessToken", '')))
                rights = 'visible'
                for key in token.keys():
                    if key == '***':
                        rights = 'visible, admin'
                    elif token[key] != 'GET' and token[key] != '' and 'visible' in token[key]:
                        rights = token[key]
                        break

                new_session()
                add("user_name", e_mail)
                add("rights", rights)
                add("schema", config.SCHEMA)
                if "expires" in js:
                    add("expires", time.mktime(time.strptime(js["expires"], '%Y-%m-%d %H:%M:%S')))
                if 'lang' in js:
                    add("app_lang", js['lang'])
                if 'role' in js:
                    add("user_role", js['role'])

                answer, ok, token_admin, lang_admin = login_admin()
                if ok:
                    add('token', token_admin)
            return txt, result
        except Exception as err:
            txt = f'Error occurred: : {err}'
            result = False
    return txt, result


def make_login(user_name, password):
    try:
        txt, result = login(user_name, password)
        if not result:
            try:
                txt = json.loads(txt)
                flash('Error login : ' + txt['detail'] + '; user_name=' + user_name, 'warning')
            except Exception as er:
                flash('Error login : ' + txt + '; user_name=' + user_name + ': ' + f"{er}", 'warning')
        return result
    except Exception as er:
        print('ERROR', 'make_login', f"{er}")
        return False


def make_upr(theme, select_language, device=''):
    """Параметры интерфейса пользователя (upr) — в сессию."""
    theme = theme if theme in colors.colors else 'white'
    add('theme', theme)
    upr = {
        'user_name': get('user_name'),
        'schema': config.SCHEMA,
        'admin': 'admin' in (get('rights') or ''),
        'theme': theme,
        'select_language': select_language or config.select_language,
        'version': version,
        'colors': colors.colors[theme],
        'time_zone': get('time_zone'),
        'device': device,
    }
    add('upr', upr)
    return upr


def user_from_chat(request, new_id=None):
    """Вход по ссылке из чат-бота (/one_new/<id>/): пользователь llm, тёмная тема, русский язык."""
    if not make_login('llm', 'llm'):
        return False
    if not exist() or 'visible' not in get('rights'):
        flash('Для пользователя {user_name} нет доступа к базе данных'.format(user_name=get('user_name')))
        return False
    info = remember_client(request)
    # у входа из чат-бота нет браузерной формы со временем — часовой пояс по IP, иначе Москва
    tz = get_timezone_hours_by_ip(info['ip'])
    add('time_zone', tz if tz is not None else 3)
    make_upr('black', 'ru')
    visits.register_login(request, get('user_name') + ' из Nasha_stengazeta')
    write_log_db('USER', 'Nasha_stengazeta', 'Вход пользователя на WEB сайт из Nasha_stengazeta ' +
                 st_system(request) + ' [' + request.environ.get('HTTP_USER_AGENT', '') + ']',
                 page=new_id, law_id=get('user_name'))
    return True


# ── Формы ──────────────────────────────────────────────────────────────────────

def init_form(request, endpoint):
    """Не вошедшего пользователя — на вход (после входа вернётся на endpoint)."""
    if not exist():
        session['page_for_return'] = endpoint
        return '/login/'


def write_log(source, request, law_id='', page=None, mes='Вход пользователя на страницу'):
    ip = get('ip')
    if ip:
        if visits.is_local(ip):
            return
        visits.register_page(source)  # в историю гостя (shared_web/visits.py)
        write_log_db('USER', source, mes, law_id=law_id, page=page, file_name=get('user_info'))


def default_form(array, answer, prefix):
    for data in array:
        default(prefix + data['key'], data['value'])
        answer[data['key']] = get(prefix + data['key'])


def save_form(array, answer, prefix):
    for data in array:
        add(prefix + data['key'], answer[data['key']])


def define_param_for_page(request, answer):
    if 'row_count' not in answer:
        return
    last_row_count = answer['row_count']
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

    if last_row_count != answer['row_count']:  # сменилось количество строк в таблице
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
        if answer.get('search') != request.form.get('search'):
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
    if 'sort' in request.form and 'selected_sort' in answer:
        sort = sql_sort(request.form.get('sort'), answer['selected_sort'])
        if answer['selected_sort'] != sort:
            answer['change_sort'] = True
            answer['change_page'] = True
        answer['selected_sort'] = sort
    if 'sort_trend0' in request.form and 'sort_trend' in answer:
        if answer['sort_trend'] != 0:
            answer['change_sort'] = True
            answer['change_page'] = True
        answer['sort_trend'] = 0
    if 'sort_trend1' in request.form and 'sort_trend' in answer:
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


def choose_language(request):
    if 'select_language' in request.form:
        upr = get('upr')
        upr['select_language'] = request.form.get('select_language')
        add('upr', upr)
    if 'select_theme_form' in request.form and request.form.get('select_theme_form') in colors.colors:
        add('theme', request.form.get('select_theme_form'))
        upr = get('upr')
        upr['theme'] = request.form.get('select_theme_form')
        upr['colors'] = colors.colors[get('theme')]
        add('upr', upr)


# ── Значения из запроса в тексте SQL ──────────────────────────────────────────────
# SQL форм выполняется через v2/execute с токеном superadmin, поэтому всё, что пришло из запроса,
# подставляется только через эти функции.
_SORT_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_.]*(::[A-Za-z_][A-Za-z0-9_ ]*)?')


def escape_sql_literal(value):
    """Значение для SQL-литерала в кавычках: апострофы удваиваются."""
    return str(value).replace("'", "''")


def sql_digits(value):
    """Целое число из запроса строкой ('' — пусто или не число)."""
    value = str(value if value is not None else '').strip()
    return value if value.isdigit() else ''


def sql_date(value, default=''):
    """Дата 'YYYY-MM-DD' из запроса; иное — default."""
    value = str(value or '').strip()
    return value if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) else default


def sql_sort(value, default):
    """Колонка сортировки ('a.sh_name', 'start_date::date'); иное — default."""
    value = str(value or '').strip()
    return value if _SORT_RE.fullmatch(value) else default


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
                where_or = where_or + "(" + st_column.format(search=escape_sql_literal(search.strip())) + ")"
            if where_or != '':
                where = where + ' and ' if where != '' else where
            where += '(' + where_or + ')'
    return where


# ── Даты ───────────────────────────────────────────────────────────────────────
# time_zone сессии — смещение пользователя от UTC в часах (как в сайтах parlaments).

def get_date_sql(st, time_zone):
    """Начало суток st (локальных для пользователя со смещением time_zone часов) — в UTC для SQL."""
    if type(st) == list:
        year, month, day = st
    else:
        year, month, day = st.split('-')
    date = datetime.datetime(int(year), int(month), int(day))
    dt = date - datetime.timedelta(hours=time_zone if time_zone else 0)
    return '{year}-{month}-{day} {hour}:{minute}:{second}'.format(
        year=dt.year, month=dt.month, day=dt.day, hour=dt.hour, minute=dt.minute, second=dt.second)


def st_today():
    return str(time.gmtime().tm_year) + '-' + str(time.gmtime().tm_mon).rjust(2, '0') + '-' + \
           str(time.gmtime().tm_mday).rjust(2, '0')


def local_today():
    """'Сегодня' по локальному времени пользователя (его time_zone)."""
    local_now = datetime.datetime.utcnow() + datetime.timedelta(hours=get('time_zone') or 0)
    return get_st_date(local_now.year, local_now.month, local_now.day)


def get_st_date(year, month, day):
    # int(): части даты приходят из запроса и идут в SQL — не число → ValueError
    return str(int(year)) + '-' + str(int(month)).rjust(2, '0') + '-' + str(int(day)).rjust(2, '0')


def calc_day(year, month, day, delta):
    dt = datetime.date(int(year), int(month), int(day)) + datetime.timedelta(days=delta)
    return dt.year, dt.month, dt.day


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


def convert_time_to_timezone(datetime_utc_str, time_zone_hours, format=None):
    """Строка даты-времени UTC → локальное время пользователя (смещение в часах), в том же или заданном формате."""
    try:
        if 'T' in datetime_utc_str:
            dt_format = "%Y-%m-%dT%H:%M:%S.%f" if '.' in datetime_utc_str else "%Y-%m-%dT%H:%M:%S"
        else:
            dt_format = "%Y-%m-%d %H:%M:%S.%f" if '.' in datetime_utc_str else "%Y-%m-%d %H:%M:%S"
        dt_local = datetime.datetime.strptime(datetime_utc_str, dt_format) + \
            datetime.timedelta(hours=time_zone_hours or 0)
        return dt_local.strftime(format or dt_format).replace('T', ' ')
    except Exception as e:
        return f"Ошибка преобразования времени: {str(e)}"


# ── Разное ─────────────────────────────────────────────────────────────────────

def define_st(txt):
    return txt if txt else ''


def translate_from_base(st):
    if st is None:
        return ''
    st = st.replace('~A~', '(').replace('~B~', ')').replace('~a1~', '@').replace('~LF~', '\n')
    st = st.replace('~a2~', ',').replace('~a3~', '=').replace('~a4~', '"').replace('~a5~', "'")
    st = st.replace('~a6~', ':').replace('~b1~', '/').replace('~b2~', '&').replace('~R~', '\r')
    return st


def get_inform_about_os():
    return f'{platform.system()}; {platform.release()}; {platform.version()};\n{platform.platform()};\n' \
           f'{platform.architecture()};\n{platform.processor()}'


def what_change(unit, current, keys=None):
    """
    Сравнивает два объекта (unit — исходное состояние, current — текущее) и возвращает
    JSON-строку с описанием различий. Поддерживает вложенные словари и списки.

    :param unit:    Исходное значение (dict, list или скаляр)
    :param current: текущее значение (dict, list или скаляр)
    :param keys:    Список ключей для отслеживания (только для dict); если None — все ключи
    :return:        JSON-строка с описанием изменений ('' если изменений нет)
    """
    if keys is not None and isinstance(unit, dict) and isinstance(current, dict):
        unit = {k: unit[k] for k in keys if k in unit}
        current = {k: current[k] for k in keys if k in current}

    def _diff(old, new):
        if isinstance(old, dict) and isinstance(new, dict):
            changes = {}
            for key in sorted(set(old) | set(new)):
                if key not in new:
                    changes[key] = {'old': old[key], 'new': None}
                elif key not in old:
                    changes[key] = {'old': None, 'new': new[key]}
                else:
                    nested = _diff(old[key], new[key])
                    if nested is not None:
                        changes[key] = nested
            return changes if changes else None
        if isinstance(old, list) and isinstance(new, list):
            if old == new:
                return None
            changes = {}
            for i in range(max(len(old), len(new))):
                if i >= len(old):
                    changes[f'[{i}]'] = {'old': None, 'new': new[i]}
                elif i >= len(new):
                    changes[f'[{i}]'] = {'old': old[i], 'new': None}
                else:
                    nested = _diff(old[i], new[i])
                    if nested is not None:
                        changes[f'[{i}]'] = nested
            return changes if changes else None
        if old != new:
            return {'old': old, 'new': new}
        return None

    if not isinstance(unit, (dict, list)) or not isinstance(current, (dict, list)):
        result = _diff(unit, current)
        return json.dumps(result if result else {}, indent=4, ensure_ascii=False)

    result = _diff(unit, current)
    return json.dumps(result, indent=4, ensure_ascii=False) if result else ''
