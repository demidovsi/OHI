"""JSON API и раздача интерфейса сайта (SPA, frontend/, React + MUI) — как в сайтах parlaments (sozd-web, kns-web).

Каждая страница реализована функцией ``prepare_form(request)`` своего модуля, которая возвращает словарь ``par``.
Здесь ``par`` отдаётся в JSON. SPA шлёт form-encoded тела с именами полей и кнопок, которые разбирает модуль формы.

Ответ любой ``/api/v2/form/<page>/``::

    {
      "par": {...},                          # данные формы
      "upr": {...},                          # параметры пользователя (имя, admin, тема, цвета)
      "messages": [[category, text], ...],   # flash-сообщения
      "redirect": "/login/" | null
    }

Сессия пользователя — подписанная cookie Flask (common.py, «Сессия пользователя»); user_id в адресах нет.
"""

import datetime
import decimal
import json
import os
import re

from flask import (Blueprint, Response, current_app, get_flashed_messages, redirect, request,
                   send_from_directory)
from werkzeug.exceptions import HTTPException

import common
import login as c_login
from common import exist, get
import analyses
import chat_logs
import new
import news_board
import rss
import search_words
from shared_web import functions as shared_functions
from shared_web import guests as shared_guests
from shared_web import logs as shared_logs

bp = Blueprint('api_v2', __name__, url_prefix='/api/v2')


# --- сериализация --------------------------------------------------------------

def _json_default(obj):
    if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
        return obj.isoformat()
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    if isinstance(obj, bytes):
        return obj.decode('utf-8', errors='replace')
    if hasattr(obj, 'item'):  # числа numpy/pandas (аналитика)
        return obj.item()
    return str(obj)


def _json_response(payload, status=200):
    body = json.dumps(payload, ensure_ascii=False, default=_json_default)
    return Response(body, status=status, mimetype='application/json')


def _upr():
    return get('upr') if exist() else None


def _respond(par):
    return _json_response({
        'par': {k: v for k, v in par.items() if k != 'redirect'},
        'upr': _upr(),
        'messages': get_flashed_messages(with_categories=True),
        'redirect': par.get('redirect'),
    })


# --- реестр форм -------------------------------------------------------------
# page -> callable(request)

FORMS = {
    'news_board': news_board.prepare_form,
    'new': new.prepare_form,
    'analyses': analyses.prepare_form,
    'chat_logs': chat_logs.prepare_form,
    'search_words': search_words.prepare_form,
    'rss': rss.prepare_form,
    'logs': shared_logs.prepare_form,
    'guests': shared_guests.prepare_form,
    'functions': shared_functions.prepare_form,
}

# Служебные формы администратора (меню «Сайт»): меню их только скрывает — права проверяются на сервере
# (main_ohi_web.admin_forms_only).
ADMIN_FORMS = ('guests', 'logs', 'functions')


# --- ошибки ------------------------------------------------------------------

@bp.errorhandler(Exception)
def _api_error(er):
    """Ошибки API — всегда JSON, а не HTML-страница."""
    current_app.logger.exception('api_v2 error')
    status = getattr(er, 'code', 500) if isinstance(er, HTTPException) else 500
    if status == 500:
        try:
            common.write_log_db('ERROR-500', 'ohi_web', 'Внутренняя ошибка сервера: ' + str(er) +
                                ' [' + request.method + ' ' + request.path + ']')
        except Exception:
            pass
    return _json_response({'error': str(er), 'type': type(er).__name__}, status=status)


# --- вход ----------------------------------------------------------------------

@bp.route('/login', methods=('POST',))
def login():
    """Вход (login.prepare_form). Поля: user_name, password, time_now ("... GMT+0300 ..."),
    theme ("white"|"black"), select_language ("ru"|"en"|"he"). Сессия — в cookie браузера."""
    st_html, st_redirect = c_login.prepare_form(request)
    messages = get_flashed_messages(with_categories=True)
    if st_html or not st_redirect or not exist():
        return _json_response({'ok': False, 'messages': messages}, status=401)
    return _json_response({'ok': True, 'upr': _upr(), 'redirect': st_redirect, 'messages': messages})


@bp.route('/me', methods=('GET',))
def me():
    upr = _upr()
    if upr is None:
        return _json_response({'ok': False}, status=401)
    return _json_response({'ok': True, 'upr': upr})


@bp.route('/logout', methods=('POST',))
def logout():
    """Выход: сессия (cookie и состояние форм на сервере) удаляется."""
    common.end_session()
    return _json_response({'ok': True})


@bp.route('/set_theme', methods=('POST',))
def set_theme():
    """Смена темы/языка без перерисовки формы (поля select_theme_form, select_language)."""
    if not exist():
        return _json_response({'ok': False}, status=401)
    common.choose_language(request)
    return _json_response({'ok': True, 'upr': _upr()})


# --- формы -------------------------------------------------------------------

@bp.route('/form/<page>/', methods=('GET', 'POST'))
def form(page):
    handler = FORMS.get(page)
    if handler is None:
        return _json_response({'error': 'unknown form: ' + page}, status=404)
    par = handler(request)
    if par is None:
        par = {}
    return _respond(par)


@bp.route('/forms', methods=('GET',))
def list_forms():
    return _json_response(sorted(FORMS.keys()))


# --- SPA ---------------------------------------------------------------------
# Интерфейс (SPA) отдаётся по всем адресам сайта, кроме /api/ и /static/; его роуты — /<page>/...
# Старые адреса классического интерфейса с user_id (/<page>/<40 hex>/...) — на тот же адрес без него.
# Ссылка из чат-бота /one_new/<id>/ — вход пользователем llm и лента новостей с открытой новостью.

_SPA_SKIP_PREFIXES = ('/api/', '/static/')
_LEGACY_UID = re.compile(r'^/([a-z_]+)/[0-9a-f]{40}(/.*)?$')
_ONE_NEW = re.compile(r'^/one_new/(\d+)/?$')
_dist_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend', 'dist')

ui = Blueprint('ui_v2', __name__)


@ui.before_app_request
def spa_entry():
    """GET-запросы страниц отдаёт SPA."""
    if request.method not in ('GET', 'HEAD'):
        return None
    path = request.path
    m = _ONE_NEW.match(path)
    if m:
        if not common.user_from_chat(request, m.group(1)):
            return redirect('/login/')
        return redirect('/news_board/?open_id=' + m.group(1))
    m = _LEGACY_UID.match(path)
    if m:
        page = m.group(1)
        target = '/' + page + '/'
        if page == 'new' and m.group(2):  # /new/<user_id>/<new_id>/ — новость в ленте новостей
            new_id = m.group(2).strip('/')
            target = '/news_board/' + ('?open_id=' + new_id if new_id.isdigit() else '')
        elif request.query_string:
            target += '?' + request.query_string.decode('latin-1')
        return redirect(target, 301)
    if path.startswith(_SPA_SKIP_PREFIXES):
        return None
    return spa(path.lstrip('/'))


def spa(path):
    """Собранный SPA (frontend/dist): файл, если есть, иначе index.html (history fallback)."""
    if path and os.path.isfile(os.path.join(_dist_dir, path)):
        return send_from_directory(_dist_dir, path)
    index = os.path.join(_dist_dir, 'index.html')
    if not os.path.isfile(index):
        return Response('frontend/dist not built. Run: cd frontend && npm run build', status=503,
                        mimetype='text/plain')
    # index.html не кэшируется: имена ресурсов с хэшем, а index должен обновиться сразу после деплоя
    resp = send_from_directory(_dist_dir, 'index.html', max_age=0)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


def register(app):
    app.register_blueprint(bp)
    app.register_blueprint(ui)
