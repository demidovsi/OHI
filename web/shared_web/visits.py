"""Учёт посетителей сайтов для формы «Гости сайта» (shared_web/guests.py) — один код для всех сайтов.

Модель данных — четыре таблицы схемы сайта (их создаёт кнопка Guests формы classes в modeler_web, объекты `emails` и `guests`):

* nsi_emails — пользователи сайта: sh_name (email), first_date, last_date, count (входов);
* nsi_guests — гости: sh_name (IP-адрес), country, city, email (пользователь, вошедший с этого адреса; пусто — аноним);
* his_guests_page — история гостя (параметр `page`): открытые страницы (название страницы), время UTC;
* his_emails_hist — история пользователя (параметр `hist`): входы — строки «LOGIN; IP=<ip>; country=<страна>; city=<город>».

Гость — пара «IP + пользователь». Локальные заходы (127.0.0.1, ::1) не учитываются, кроме счётчика входов пользователя.
Модуль работает с модулями сайта `config` (SCHEMA) и `common` (get, add, send_rest), см. shared_web/README.md.
"""
import datetime
import json

import common
import config

_LOCAL_IPS = ('127.0.0.1', '::1', 'localhost')
_geo_cache = {}  # ip -> (страна, город)


def client_ip(request):
    """IP клиента: первый адрес X-Forwarded-For (дальше в цепочке — прокси, например nginx домена), иначе адрес
    соединения."""
    forwarded = request.environ.get('HTTP_X_FORWARDED_FOR', '')
    ip = forwarded.split(',')[0].strip() if forwarded else ''
    return ip or (request.remote_addr or '')


def is_local(ip):
    return not ip or ip in _LOCAL_IPS


def geo(ip):
    """(страна, город) по IP (ip-api.com, по-русски, с кэшем); для локальных адресов и при ошибке — ('', '')."""
    if is_local(ip):
        return '', ''
    if ip not in _geo_cache:
        try:
            import requests
            r = requests.get(f'http://ip-api.com/json/{ip}?lang=ru', timeout=5)
            data = r.json() if r.ok else {}
        except Exception:
            return '', ''
        if data.get('status') != 'success':
            return '', ''
        _geo_cache[ip] = (data.get('country', ''), data.get('city', ''))
    return _geo_cache[ip]


def _now():
    """Текущее время UTC для записи в таблицы (YYYY-MM-DD HH:MM:SS)."""
    return datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')


def _sql(text):
    """Строка для литерала SQL: апострофы удваиваются."""
    return str(text).replace("'", "''")


def _select(table, where):
    """Строки таблицы схемы сайта по условию; None — ошибка REST."""
    ans, ok, _ = common.send_rest(f"v2/select/{config.SCHEMA}/{table}?where={where}", token_user=common.get('token'))
    if not ok:
        print(f'visits: {table}', ans, flush=True)
        return None
    return json.loads(ans)


def _entity(object_code, values):
    """Запись объекта (создание, если нет values['id'], иначе коррекция); id объекта или None (ошибка REST)."""
    params = {'schema_name': config.SCHEMA, 'object_code': object_code, 'values': values}
    ans, ok, _ = common.send_rest('v3/entity', 'PUT', params=params, token_user=common.get('token'))
    if not ok:
        print(f'visits: {object_code}', ans, flush=True)
        return None
    try:
        return json.loads(ans)[0]['id']
    except (ValueError, KeyError, IndexError, TypeError):
        return values.get('id')


def _history(object_code, param_code, object_id, value):
    """Запись в историю объекта (his_<объект>_<параметр>)."""
    value = str(value).replace("'", '"')
    url = f"v1/MDM/his/{config.SCHEMA}/{object_code}/{param_code}/{object_id}?value='{value}'"
    ans, ok, _ = common.send_rest(url, 'POST', token_user=common.get('token'))
    if not ok:
        print(f'visits: history {object_code}.{param_code}', ans, flush=True)


def _email_id(user_name):
    """Пользователь в nsi_emails: нет — заводится, есть — число входов растёт, последний вход обновляется. None — ошибка REST."""
    rows = _select('nsi_emails', f"sh_name='{_sql(user_name)}'")
    if rows is None:
        return None
    now = _now()
    if rows:
        row = rows[0]
        _entity('emails', {'id': row['id'], 'count': (row.get('count') or 0) + 1, 'last_date': now})
        return row['id']
    return _entity('emails', {'sh_name': user_name, 'first_date': now, 'last_date': now, 'count': 1})


def _guest_id(ip, email_id):
    """id гостя «IP + пользователь» (email_id None — аноним); нет — заводится (страна и город — по IP). None — ошибка REST."""
    who = f'email={int(email_id)}' if email_id else 'email is null'
    rows = _select('nsi_guests', f"sh_name='{_sql(ip)}' and {who}")
    if rows is None:
        return None
    if rows:
        return rows[0]['id']
    country, city = geo(ip)
    values = {'sh_name': ip, 'country': country, 'city': city}
    if email_id:
        values['email'] = int(email_id)
    return _entity('guests', values)


def register_guest(request):
    """Гость текущего запроса (по IP и вошедшему пользователю) → в сессию (guest_id); возвращает его id (None — локальный
    заход или ошибка)."""
    ip = client_ip(request)
    if is_local(ip):
        return None
    guest_id = _guest_id(ip, common.get('email_id'))
    if guest_id is not None:
        common.add('guest_id', guest_id)
    return guest_id


def register_login(request, user_name):
    """Вход пользователя: nsi_emails (число входов, последний вход), гость «IP + пользователь» и запись
    `LOGIN; IP=...; country=...; city=...` в историю пользователя (his_emails_hist)."""
    email_id = _email_id(user_name)
    if email_id is None:
        return
    common.add('email_id', email_id)
    ip = client_ip(request)
    if is_local(ip):
        return
    guest_id = _guest_id(ip, email_id)
    if guest_id is None:
        return
    common.add('guest_id', guest_id)
    country, city = geo(ip)
    _history('emails', 'hist', email_id, f'LOGIN; IP={ip}; country={country}; city={city}')


def register_page(name_page):
    """Открытие страницы вошедшим пользователем — в историю его гостя (если гость определён при входе)."""
    guest_id = common.get('guest_id')
    if guest_id:
        _history('guests', 'page', guest_id, name_page)
