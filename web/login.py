import json

from flask import flash, session
from user_agents import parse

import common
from shared_web import visits
from common import exist, get, write_log_db, add

HOME_PAGE = '/news_board/'  # страница после входа, если пользователь не пришёл с другой (HOME_PAGE в frontend/src/menu.ts)


def prepare_form(request) -> tuple[str, str]:
    """
    Вход пользователя (POST /api/v2/login; формы входа на сервере больше нет — она в SPA).

    Поля: user_name, password, time_now (строка Date браузера, «... GMT+0300 ...»), theme ("white"|"black"),
    select_language ("ru"|"en"|"he").

    В сессию: ip, country, city, os, browser, user_info «IP; страна; город» (для file_name записей журнала), time_zone (смещение от UTC
    в часах), theme, upr (параметры интерфейса). После входа — запись LOGIN в журнал и вход в историю гостя.

    Returns:
        ``(template, redirect)``: при ошибке — ``('login.html', '')``; при успехе — ``('', путь)``, где путь —
        страница, с которой пришёл не вошедший пользователь (``session['page_for_return']``), или ``HOME_PAGE``.
    """
    user_agent = request.headers.get('User-Agent', '')
    device = 'Mobile device' if any(m in user_agent for m in ['Mobi', 'Android', 'iPhone', 'iPad']) else 'Desktop device'
    if request.method != 'POST':
        return 'login.html', ''
    # куда вернуться после входа — запомнить до входа: вход начинает новую сессию (cookie очищается)
    page_for_return = session.pop('page_for_return', None)
    if not common.make_login(request.form.get('user_name'), request.form.get('password')):
        return 'login.html', ''
    if not exist() or 'visible' not in get('rights'):
        flash('Для пользователя {user_name} нет доступа к базе данных'.format(user_name=get('user_name')))
        return 'login.html', ''
    client_info = common.remember_client(request)
    try:
        time_zone = int(request.form.get('time_now').split('GMT')[1].split('(')[0][:3])
    except Exception:
        time_zone = 0
    add('time_zone', time_zone)
    common.make_upr(request.form.get('theme'), request.form.get('select_language'), device)

    # гость (по IP) и вход — в историю гостя (общий учёт посетителей shared_web/visits.py)
    visits.register_login(request, get('user_name'))

    if common.ip_good(request):
        ua = parse(user_agent)
        write_log_db('LOGIN', 'ohi_web',
                     msg='Вход пользователя на WEB сайт\n' +
                         json.dumps({
                             "browser": client_info['browser'],
                             "browser_version": ua.browser.version_string,
                             "os": ua.os.family,
                             "os_version": ua.os.version_string,
                             "device": ua.device.family,
                             "is_mobile": ua.is_mobile,
                             "is_tablet": ua.is_tablet,
                             "is_pc": ua.is_pc,
                             "is_bot": ua.is_bot,
                         }, ensure_ascii=False, indent=4),
                     law_id=get('user_name'))

    return '', page_for_return or HOME_PAGE
