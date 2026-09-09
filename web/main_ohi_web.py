import os
import datetime
import socket

from flask import Flask, render_template, request, flash, redirect, jsonify, get_flashed_messages, url_for
from flask_moment import Moment

import config
import common
from common import get, add
import login as c_login
import logs as c_logs
import functions as c_functions
import delete_unit as c_delete_unit
import new as c_new
import guests as c_guests
import search_words as c_search_words
import rss as c_rss
import analyses as c_analyses
import news_board as c_news_board
import users_session
import language
import chat_logs as c_chat_logs

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(20).hex()
app.config['CSRF_ENABLED'] = True
app.permanent = True
app.permanent_session_lifetime = datetime.timedelta(hours=24)


@app.route('/')
def index():
    return redirect('/login/')


@app.route('/login/', methods=('GET', 'POST'))
def login():
    user_agent = request.headers.get('User-Agent', '')
    if any(mobile in user_agent for mobile in ['Mobi', 'Android', 'iPhone', 'iPad']):
        user_agent = "Mobile device"
    else:
        user_agent = "Desktop device"
    st_html, st_redirect = c_login.prepare_form(request)
    if st_html:
        return render_template(st_html, languages=config.languages, select_language=config.select_language, version=common.version, user_agent=user_agent)
    else:
        return redirect(st_redirect)


@app.route('/api/set_theme/<user_id>/', methods=('POST',))
def api_set_theme(user_id):
    # Кнопка-тумблер темы (static/js/theme_switch.js) переключает тему только
    # на клиенте (localStorage), без похода на сервер - без этого upr['colors']
    # оставался бы устаревшим до следующего обычного сабмита формы, и страницы
    # при переходе рисовались бы в уже неактуальной теме. Лёгкий
    # fire-and-forget POST сюда сразу же синхронизирует серверное состояние -
    # переиспользует ту же логику, что и обычный сабмит с select_theme_form.
    common.choose_language(user_id, request)
    users_session.users.save()
    return '', 204


@app.route('/delete_unit/<user_id>/', methods=('GET', 'POST'))
def delete_unit(user_id):
    try:
        if request.method == 'POST':
            users_session.users.load()
            c_delete_unit.prepare_form(user_id, request)
            if get(user_id, 'page_for_return') is not None:
                st = get(user_id, 'page_for_return')
                add(user_id, 'page_for_return', None)
                users_session.users.save()
                return redirect(st)
            else:
                return redirect('/login/')
        return render_template(
            'delete_unit.html', user_id=user_id,
            theme=get(user_id, 'theme'), colors=get(user_id, 'upr')['colors'],
            confirmation_text=get(user_id, 'confirmation_text'),
            question_text=get(user_id, 'question_text')
        )
    except:
        return redirect('/login/')


@app.route('/logs/<user_id>/', methods=('GET', 'POST'))
def logs(user_id):
    par = c_logs.prepare_form(user_id, request)
    users_session.users.save()
    if 'redirect' in par:
        return redirect(par['redirect'])
    return render_template(
        'logs.html', colors=get(user_id, 'upr')['colors'], upr=get(user_id, 'upr'), par=par,
        own='logs', menu_txt=language.get_lang(user_id, 'menu', language.menu),
        txt=language.get_lang(user_id, 'log', language.log), languages=config.languages)


@app.route('/chat_logs/<user_id>/', methods=('GET', 'POST'))
def chat_logs(user_id):
    par = c_chat_logs.prepare_form(user_id, request)
    users_session.users.save()
    if 'redirect' in par:
        return redirect(par['redirect'])
    return render_template(
        'chat_logs.html', colors=get(user_id, 'upr')['colors'], upr=get(user_id, 'upr'), par=par,
        menu_txt=language.get_lang(user_id, 'menu', language.menu),
        txt=language.get_lang(user_id, 'chat_logs', language.chat_logs),
        own='chat_logs', languages=config.languages)


@app.route('/news_board/<user_id>/', methods=('GET', 'POST'))
def news_board(user_id):
    par = c_news_board.prepare_form(user_id, request)
    users_session.users.save()
    if 'redirect' in par:
        return redirect(par['redirect'])
    return render_template(
        'news_board.html', colors=get(user_id, 'upr')['colors'], upr=get(user_id, 'upr'), par=par,
        user_id=user_id, own='news_board', menu_txt=language.get_lang(user_id, 'menu', language.menu),
        txt=language.get_lang(user_id, 'news_board', language.news_board),
        languages=config.languages)


@app.route('/api/news_board/<user_id>/data', methods=('GET',))
def api_news_board_data(user_id):
    st = common.init_form(user_id, request, '/news_board/')
    if st:
        return jsonify(redirect=st)
    date_str = request.args.get('date', common.st_today())
    try:
        year, month, day = (int(x) for x in date_str.split('-'))
    except Exception:
        return jsonify(error='bad date'), 400
    rows = c_news_board.load_day(user_id, year, month, day)
    users_session.users.save()
    return jsonify(date=date_str, count=len(rows), rows=rows,
                   messages=get_flashed_messages(with_categories=True))


@app.route('/api/news_board/<user_id>/find/<int:news_id>', methods=('GET',))
def api_news_board_find(user_id, news_id):
    st = common.init_form(user_id, request, '/news_board/')
    if st:
        return jsonify(redirect=st)
    date_str = c_news_board.find_date(user_id, news_id)
    users_session.users.save()
    if not date_str:
        return jsonify(found=False)
    return jsonify(found=True, date=date_str)


@app.route('/api/news_board/<user_id>/delete/<int:news_id>', methods=('POST',))
def api_news_board_delete(user_id, news_id):
    st = common.init_form(user_id, request, '/news_board/')
    if st:
        return jsonify(redirect=st)
    upr = get(user_id, 'upr')
    if not upr or not upr.get('admin'):
        return jsonify(error='forbidden'), 403
    c_news_board.delete_new(user_id, news_id)
    users_session.users.save()
    return jsonify(ok=True)


@app.route('/api/new_board/<user_id>/<new_id>/', methods=('GET', 'POST'))
def api_new_board(user_id, new_id):
    """Та же логика, что и у страницы /new/ (просмотр/редактирование/перевод/
    сохранение новости) - переиспользуем c_new.prepare_form как есть, только
    отдаём JSON вместо HTML. Используется модальным окном news_board.js,
    чтобы открыть новость без перехода на отдельную страницу (и без потери
    состояния фильтров/скролла в news_board)."""
    par = c_new.prepare_form(user_id, request, new_id)
    users_session.users.save()
    if 'redirect' in par:
        return jsonify(redirect=par['redirect'])
    unit = par['unit']
    return jsonify(
        new_id=par['new_id'],
        select_lang=par['select_lang'],
        languages=par['languages'],
        admin=bool(get(user_id, 'upr') and get(user_id, 'upr').get('admin')),
        unit={
            'id': unit.get('id'),
            'lang': unit.get('lang'),
            'name_rss': unit.get('name_rss'),
            'public_date': unit.get('public_date'),
            'name_theme': unit.get('name_theme'),
            'title': unit.get('title'),
            'title_init': unit.get('title_init'),
            'description': unit.get('description'),
            'description_init': unit.get('description_init'),
            'full': unit.get('full'),
            'full_init': unit.get('full_init'),
            'url': unit.get('url'),
            'meta_img': unit.get('meta_img'),
            'author': unit.get('author'),
            'file': unit.get('file'),
            # чтобы модалка news_board.js могла точечно обновить строку
            # таблицы (все языковые варианты сразу) без перезапроса дня
            'title_ru': unit.get('title_ru'),
            'title_en': unit.get('title_en'),
            'title_he': unit.get('title_he'),
            'description_ru': unit.get('description_ru'),
            'description_en': unit.get('description_en'),
            'description_he': unit.get('description_he'),
        },
        messages=get_flashed_messages(with_categories=True))


@app.route('/new/<user_id>/<new_id>/', methods=('GET', 'POST'))
def new(user_id, new_id):
    par = c_new.prepare_form(user_id, request, new_id)
    users_session.users.save()
    if 'redirect' in par:
        return redirect(par['redirect'])
    return render_template(
        'new.html', colors=get(user_id, 'upr')['colors'], upr=get(user_id, 'upr'), par=par,
        own='new', menu_txt=language.get_lang(user_id, 'menu', language.menu),
        txt=language.get_lang(user_id, 'new', language.new), languages=config.languages)


@app.route('/functions/<user_id>/', methods=('GET', 'POST'))
def functions(user_id):
    par = c_functions.prepare_form(user_id, request)
    users_session.users.save()
    if 'redirect' in par:
        return redirect(par['redirect'])
    return render_template(
        "functions.html", colors=get(user_id, 'upr')['colors'], upr=get(user_id, 'upr'), par=par,
        user_id=user_id, own='functions', menu_txt=language.get_lang(user_id, 'menu', language.menu),
        txt=language.get_lang(user_id, 'functions', language.functions), languages=config.languages)


@app.route('/api/functions/<user_id>/data', methods=('POST',))
def api_functions_data(user_id):
    par = c_functions.prepare_form(user_id, request)
    users_session.users.save()
    if 'redirect' in par:
        return jsonify(redirect=par['redirect'])

    colors = get(user_id, 'upr')['colors']
    upr = get(user_id, 'upr')
    functions_txt = language.get_lang(user_id, 'functions', language.functions)
    return jsonify(
        table_html=render_template('include/functions_table.html', par=par, colors=colors, upr=upr, txt=functions_txt),
        options_html=render_template('include/functions_options.html', par=par, colors=colors),
        existing_idents=[f['sh_name'] for f in par['functions'] if f.get('sh_name')],
        name_function=par.get('name_function', ''),
        description_function=par.get('description_function', ''),
        messages=get_flashed_messages(with_categories=True),
        scroll=par.get('scroll', 0),
    )


@app.route('/guests/<user_id>/', methods=('GET', 'POST'))
def guests(user_id):
    par = c_guests.prepare_form(user_id, request)
    users_session.users.save()
    if 'redirect' in par:
        return redirect(par['redirect'])
    return render_template(
        "guests.html", colors=get(user_id, 'upr')['colors'], upr=get(user_id, 'upr'), par=par,
        user_id=user_id, menu_txt=language.get_lang(user_id, 'menu', language.menu), languages=config.languages,
        txt=language.get_lang(user_id, 'guests', language.guests),
        own='guests')


@app.route('/api/guests/<user_id>/data', methods=('POST',))
def api_guests_data(user_id):
    par = c_guests.prepare_form(user_id, request)
    users_session.users.save()
    if 'redirect' in par:
        return jsonify(redirect=par['redirect'])

    colors = get(user_id, 'upr')['colors']
    upr = get(user_id, 'upr')
    guests_txt = language.get_lang(user_id, 'guests', language.guests)
    return jsonify(
        top_html=render_template('include/guests_top.html', par=par, colors=colors, upr=upr,
                                 menu_txt=language.get_lang(user_id, 'menu', language.menu),
                                 languages=config.languages, txt=guests_txt),
        table_html=render_template('include/guests_table.html', par=par, colors=colors, upr=upr, txt=guests_txt),
        pages_html=render_template('include/pages_table.html', par=par, colors=colors, own='guests',
                                   menu_txt=language.get_lang(user_id, 'menu', language.menu)),
        chart_json=par.get('chart_json', '{}'),
        chart_title=par.get('chart_title', ''),
        view_mode=par.get('view_mode', 'guests'),
        messages=get_flashed_messages(with_categories=True),
        scroll=par.get('scroll', 0),
    )


@app.route('/one_new/<new_id>/', methods=('GET', 'POST'))
def one_new(new_id):
    ok, user_id = common.user_from_chat(request, new_id)
    if not ok:
        return render_template('login.html')
    language.load_lang()  # загрузить языки
    users_session.users.load()
    add(user_id, 'theme', 'black')
    upr = get(user_id, 'upr')
    upr['select_language'] = 'ru'
    users_session.users.save()
    # Раньше вело сразу на отдельную страницу /new/ - теперь новость
    # открывается модально поверх news_board (news_board.js: applyOpenIdParam),
    # как и при обычном клике по строке в списке новостей.
    return redirect('/news_board/{user_id}/?open_id={new_id}'.format(user_id=user_id, new_id=new_id))


@app.route('/search_words/<user_id>/', methods=('GET', 'POST'))
def search_words(user_id):
    par = c_search_words.prepare_form(user_id, request)
    users_session.users.save()
    if 'redirect' in par:
        return redirect(par['redirect'])
    if 'flash' in par:
        flash(par['flash'], 'warning')
    else:
        return render_template(
            "search_words/search_words.html", colors=get(user_id, 'upr')['colors'], upr=get(user_id, 'upr'), par=par,
            menu_txt=language.get_lang(user_id, 'menu', language.menu), languages=config.languages,
            txt=language.get_lang(user_id, 'search_words', language.search_words),
            own='search_words')


@app.route('/rss/<user_id>/', methods=('GET', 'POST'))
def rss(user_id):
    par = c_rss.prepare_form(user_id, request)
    users_session.users.save()
    if 'redirect' in par:
        return redirect(par['redirect'])
    if 'flash' in par:
        flash(par['flash'], 'warning')
    else:
        return render_template(
            "rss.html", colors=get(user_id, 'upr')['colors'], upr=get(user_id, 'upr'), par=par,
            menu_txt=language.get_lang(user_id, 'menu', language.menu), languages=config.languages,
            txt=language.get_lang(user_id, 'rss', language.rss),
            own='search_words')


@app.route('/analyses/<user_id>/', methods=('GET', 'POST'))
def analyses(user_id):
    par = c_analyses.prepare_form(user_id, request)
    users_session.users.save()
    if 'redirect' in par:
        return redirect(par['redirect'])
    if request.method == 'POST':
        # POST/Redirect/GET - без этого страница-результат POST остаётся
        # последней записью в истории браузера, и обновление (в т.ч. Ctrl+F5)
        # может повторно отправить ту же форму - включая button_to_left/right,
        # из-за чего заданный интервал дат сдвигался бы ещё раз в ту же сторону.
        return redirect(url_for('analyses', user_id=user_id))
    if 'flash' in par:
        flash(par['flash'], 'warning')
    else:
        return render_template(
            "analyses.html", colors=get(user_id, 'upr')['colors'], upr=get(user_id, 'upr'), par=par,
            menu_txt=language.get_lang(user_id, 'menu', language.menu),
            languages=config.languages,
            txt=language.get_lang(user_id, 'analyses', language.analyses),
            own='analyses')


@app.errorhandler(500)
def handle_internal_error(e):
    # Вместо голого текста Werkzeug "The server encountered an internal
    # error..." - понятная страница с указанием, что делать дальше. Логируем
    # исходную ошибку в БД (как остальные события в приложении), но не даём
    # сбою самого логирования превратить это в повторную 500-ю.
    try:
        common.write_log_db('ERROR-500', 'ohi_web', 'Внутренняя ошибка сервера: ' + str(e) +
                            ' [' + request.method + ' ' + request.path + ']')
    except Exception:
        pass
    return render_template(
        'error.html', code=500, title='Что-то пошло не так', back_url=None,
        message='Произошла внутренняя ошибка сервера. Мы уже записали её в лог. '
                'Попробуйте обновить страницу через минуту или начните заново с главной.'
    ), 500


@app.errorhandler(404)
def handle_not_found(e):
    return render_template(
        'error.html', code=404, title='Страница не найдена', back_url=None,
        message='Такой страницы не существует - возможно, ссылка устарела или введена с ошибкой.'
    ), 404


common.current_path = os.path.abspath(os.curdir)
users_session.users = users_session.Session()
moment = Moment(app)

ip = socket.gethostbyname(socket.gethostname())
country, city, is_ok = common.define_guest(ip)
st = '\n({country}, {city})'.format(country=country, city=city) if is_ok and country else ''
common.write_log_db('START WEB', 'Старт сайта', socket.gethostname() + '\n' + common.get_inform_about_os(),
                    law_id='OHI-web', file_name='IP=' + ip + st)
language.load_list_languages()

if __name__ == '__main__':
    if os.path.exists('static/session.json'):
        os.remove('static/session.json')
    app.run(port=config.OWN_PORT, host=config.OWN_HOST)
