"""Учёт посетителей сайтов для формы «Гости сайта» (shared_web/guests.py) — один код для всех сайтов.

Гость — IP-адрес клиента (таблица nsi_guests схемы сайта, объект `guests`), его история (his_guests_page, параметр
`page`) — вход `Login (<пользователь>)` и открытые страницы (название страницы). По записям `Login (...)` форма
строит режим «Пользователи».

Модуль работает с модулями сайта `config` (SCHEMA) и `common` (get, add, send_rest), см. shared_web/README.md.
Локальные заходы (127.0.0.1, ::1) не учитываются, как и раньше в kns-web.
"""
import json

import common
import config

_LOCAL_IPS = ('127.0.0.1', '::1', 'localhost')
_geo_cache = {}  # ip -> (страна, город)


def client_ip(request):
    """IP клиента: первый адрес X-Forwarded-For (дальше в цепочке — прокси, например nginx домена), иначе адрес
    соединения. Прежде в sozd-web гостем записывалась вся цепочка «клиент,прокси», и страна не определялась."""
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


def _guest_id(ip):
    """id гостя с этим IP; нет — заводится (страна и город — по IP). None — ошибка REST."""
    ip_sql = ip.replace("'", "''")
    ans, ok, _ = common.send_rest(f"v2/select/{config.SCHEMA}/nsi_guests?where=sh_name='{ip_sql}'",
                                  token_user=common.get('token'))
    if not ok:
        print('visits: nsi_guests', ans, flush=True)
        return None
    rows = json.loads(ans)
    if rows:
        return rows[0]['id']
    country, city = geo(ip)
    params = {'schema_name': config.SCHEMA, 'object_code': 'guests',
              'values': {'sh_name': ip, 'country': country, 'city': city}}
    ans, ok, _ = common.send_rest('v3/entity', 'PUT', params=params, token_user=common.get('token'))
    if not ok:
        print('visits: new guest', ans, flush=True)
        return None
    return json.loads(ans)[0]['id']


def _history(guest_id, value):
    """Запись в историю гостя (his_guests_page)."""
    value = str(value).replace("'", '"')
    url = f"v1/MDM/his/{config.SCHEMA}/guests/page/{guest_id}?value='{value}'"
    ans, ok, _ = common.send_rest(url, 'POST', token_user=common.get('token'))
    if not ok:
        print('visits: history', ans, flush=True)


def register_guest(request):
    """Гость текущего запроса (по IP) → в сессию (guest_id); возвращает его id (None — локальный заход или ошибка)."""
    ip = client_ip(request)
    if is_local(ip):
        return None
    guest_id = _guest_id(ip)
    if guest_id is not None:
        common.add('guest_id', guest_id)
    return guest_id


def register_login(request, user_name):
    """Вход пользователя: гость (по IP) и запись `Login (<пользователь>)` в его историю."""
    guest_id = register_guest(request)
    if guest_id is not None:
        _history(guest_id, f'Login ({user_name})')


def register_page(name_page):
    """Открытие страницы вошедшим пользователем — в историю его гостя (если гость определён при входе)."""
    guest_id = common.get('guest_id')
    if guest_id:
        _history(guest_id, name_page)
