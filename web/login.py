from flask import flash, session

import common
from common import exist, get, write_log_db, add
import users_session
import colors
import language


def prepare_form(request):
    if request.method == 'POST':
        ok, user_id = common.make_login(request.form.get('user_name'), request.form.get('password'),
                                        common.st_address(request))
        if not ok:
            return 'login.html', ''
        if not exist(user_id) or 'visible' not in get(user_id, 'rights'):
            flash('Для пользователя {user_name} нет доступа к базе данных'.format(
                user_name=get(user_id, 'user_name')))
            return 'login.html', ''
        users_session.users.load()
        common.create_user_address(user_id, request)
        # записать в public login пользователя
        common.get_guest(user_id, common.st_address(request))
        time_zone_hour = int(request.form.get('time_now').split('GMT')[1].split('(')[0][:3])
        time_zone_min = int(request.form.get('time_now').split('GMT')[1].split('(')[0][3:5])
        time_zone = (int(time_zone_hour) * 60 + int(time_zone_min))  # в минутах
        add(user_id, 'time_zone', time_zone)
        add(user_id, 'theme', request.form.get('select_theme'))

        upr = {
            'user_name': get(user_id, 'user_name'),
            'user_id': user_id,
            'schema': get(user_id, 'schema'),
            'admin': 'admin' in get(user_id, 'rights'),
            'theme': request.form.get('select_theme'),
            'select_theme': request.form.get('select_theme'),
            'version': common.version,
            'colors': colors.colors[get(user_id, 'theme')],
            'time_zone': get(user_id, 'time_zone'),
            'select_language': request.form.get('select_language')
        }
        add(user_id, 'upr', upr)
        users_session.users.save()
        language.load_lang()  # загрузить языки

        if common.ip_good(request):
            write_log_db(
                'USER',
                'LOGIN', 'Вход пользователя на WEB сайт' + ' [' + request.environ.get('HTTP_USER_AGENT') + ']',
                file_name=get(user_id, 'user_address'),
                law_id=request.form.get('user_name'))

        # зафиксировать лог пользователя
        common.fix_login(common.st_address(request),
                         'Login ({user_name})'.format(user_name=get(user_id, 'user_name')))

        if 'page_for_return' in session:
            st = session['page_for_return']
            session.pop('page_for_return')
            return '', st + user_id + '/'
        else:
            return '', '/logs/{user_id}/'.format(user_id=user_id)
    return 'login.html', ''
