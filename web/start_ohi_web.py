"""Точка входа сайта OHI (web/).

Локально (PyCharm: Run → этот файл; или python start_ohi_web.py из любой папки) — встроенный сервер Flask на
OHI_WEB_HOST:PORT (по умолчанию 127.0.0.1:8082); в Cloud Run — gunicorn start_ohi_web:app (Dockerfile).
Интерфейс — SPA (frontend/dist, собирается npm run build), API — api_v2.py. Устройство — как у сайтов parlaments
(sozd-web, kns-web); общие формы Log / Гости сайта / Параметры сервисов — копия parlaments/shared_web (shared_web/).
"""
import os

# Рабочая директория — папка приложения (frontend/dist, временные файлы cloud.py ищутся относительно неё),
# поэтому переходим сюда до импорта остальных модулей — запуск возможен из любой папки.
_here = os.path.dirname(os.path.abspath(__file__))
os.chdir(_here)

import datetime
import re
import socket

from flask import Flask, jsonify, request

import common
import config

app = Flask(__name__)
# Сессия пользователя — подписанная cookie Flask (см. common.py, «Сессия пользователя»). Ключ подписи постоянный
# (FLASK_SECRET_KEY: локально — web/.env, в Cloud Run — Secret Manager), иначе после перезапуска или на другом
# экземпляре cookie недействительна и пользователь «вылетает».
_secret = os.environ.get('FLASK_SECRET_KEY', '')
if not _secret:
    print('WARNING: не задан FLASK_SECRET_KEY — сессии не переживут перезапуск процесса', flush=True)
    _secret = os.urandom(32).hex()
app.config['SECRET_KEY'] = _secret
app.config['SESSION_COOKIE_NAME'] = 'ohi_session'  # не пересекается с cookie других сайтов на одном localhost
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = bool(os.environ.get('K_SERVICE'))  # Cloud Run — только https
app.permanent_session_lifetime = datetime.timedelta(hours=24)

import api_v2  # noqa: E402

# Служебные формы администратора (меню «Сайт»): меню их только скрывает — права проверяются здесь.
# Без входа пропускаем: форма сама вернёт redirect на /login/.
_ADMIN_FORMS = re.compile(r'^/api/v2/form/(?:' + '|'.join(api_v2.ADMIN_FORMS) + r')(?:/|$)')


@app.before_request
def admin_forms_only():
    if not _ADMIN_FORMS.match(request.path) or not common.exist() or common.is_admin():
        return None
    return jsonify(error='forbidden'), 403


# JSON API + интерфейс (SPA, frontend/dist) — по всем адресам сайта, см. api_v2.py
api_v2.register(app)

common.current_path = os.path.abspath(os.curdir)

_ip = socket.gethostbyname(socket.gethostname())
common.write_log_db('START WEB', 'Старт сайта', socket.gethostname() + '\n' + common.get_inform_about_os() +
                    '\n' + common.version, law_id='OHI-web', file_name='IP=' + _ip)

if __name__ == '__main__':
    from shared_web import spa_build
    spa_build.ensure_built(_here)  # локально: пересобрать frontend/dist, если исходники новее (SPA_BUILD=0 — нет)
    app.run(port=config.OWN_PORT, host=config.OWN_HOST)
