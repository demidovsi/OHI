"""
Общие утилиты сервера мониторинга СМИ.

Содержит функции для: авторизации, REST-запросов, логирования в БД,
работы с конфигурацией, отправки в Telegram, поиска поисковых образов,
записи новостей в БД и облако, парсинга дат.
"""
import email.utils
import html as html_module
import socket
import time
import datetime
import threading
import config

import requests
import json
import re
from requests.exceptions import HTTPError

from ohi_shared.text_utils import decode, encode, str1000, get_duration  # noqa: F401

SRC = 'llm-server'

# Персистентная HTTP-сессия для REST-запросов к серверу.
# Переиспользует TCP-соединения и connection pool вместо создания нового Session на каждый запрос.
_rest_session = requests.Session()
current_path = ''
count_tg_ok = 0     # счётчик успешных отправок в Telegram
count_tg_err = 0    # счётчик ошибок отправки в Telegram

# Кэш токена администратора: обновляется не чаще одного раза в _TOKEN_TTL секунд
_TOKEN_TTL = 3600           # время жизни токена, секунд
_token_cache = ''
_token_lang_cache = ''
_token_expire = 0.0
_token_lock = threading.Lock()


def get_value_config_param(key, par, default=None):
    """Возвращает значение параметра конфигурации по коду. Числовые — как int."""
    for unit in par:
        if unit['code'] == key:
            if 'is_number' not in unit or unit['is_number']:
                return int(unit['value'])
            return unit['value']
    return default


def get_difference(caption, value_old, value):
    """Возвращает строку изменения параметра (old -> new), если значение изменилось."""
    if value != value_old:
        return caption + ': ' + str(value_old) + ' -> ' + str(value) + '; \n'
    else:
        return ''


def get_param_work(caption, value):
    """Форматирует строку «caption: value» для вывода текущих параметров."""
    return caption + ': ' + str(value) + '; \n'


def get_param_telegram():
    """Загружает параметры Telegram-бота (token_bot, chat_id) из конфигурации БД."""
    par = load_config_params('TG')
    token_bot = decode('abcd', get_value_config_param('token_bot', par))
    chat_id = get_value_config_param('chat_id', par)
    return token_bot, chat_id


def get_difference_config_params(par, answer):
    """Сравнивает текущие и новые параметры конфигурации. Возвращает (изменения, текущие значения)."""
    st_difference = ''
    st_param_work = ''
    for data in par:
        for unit in answer:
            if unit['code'] == data['code']:
                data['is_number'] = unit['is_number']
                if data['value'] != unit['value']:
                    st_difference += get_difference(unit['sh_name'], data['value'], unit['value'])
                data['value'] = unit['value']
                st_param_work += get_param_work(unit['sh_name'], unit['value'])
                break
    return st_difference, st_param_work


_geo_cache = None  # кэш геолокации: (country, city)


def _get_geo():
    """Определяет страну и город по внешнему IP через ip-api.com. Результат кэшируется."""
    global _geo_cache
    if _geo_cache is None:
        try:
            resp = requests.get('http://ip-api.com/json/?fields=country,city', timeout=5)
            if resp.ok:
                js = resp.json()
                _geo_cache = (js.get('country', ''), js.get('city', ''))
            else:
                _geo_cache = ('', '')
        except Exception:
            _geo_cache = ('', '')
    return _geo_cache


_computer_name_cache = None  # кэш: имя хоста не меняется за время работы процесса


def get_computer_name():
    """Возвращает имя компьютера, IP, страну и город в формате 'hostname; ip; country; city'."""
    global _computer_name_cache
    if _computer_name_cache is not None:
        return _computer_name_cache
    hostname = socket.gethostname()
    ip = socket.gethostbyname(hostname)
    ip = '' if ip == '127.0.0.1' else ip
    country, city = _get_geo()
    geo = '; '.join(filter(None, [country, city]))
    result = hostname + '; ' + ip
    if geo:
        result += '; ' + geo
    _computer_name_cache = result
    return _computer_name_cache


def invalidate_token_cache():
    """Сбрасывает кэш токена (вызывается при получении 401 от сервера)."""
    global _token_cache, _token_lang_cache, _token_expire
    with _token_lock:
        _token_cache = ''
        _token_lang_cache = ''
        _token_expire = 0.0


# Признаки временной недоступности PostgreSQL (рестарт, переключение реплики и т.п.)
_TRANSIENT_DB_ERRORS = (
    'SSL SYSCALL error',
    'connection to server',
    'could not connect to server',
    'server closed the connection unexpectedly',
    'ECONNREFUSED',
    'the database system is starting up',
    'Connection aborted',
    'RemoteDisconnected',
    'Remote end closed connection',
)

# Подстроки в тексте исключения, при которых стоит повторить запрос к серверу.
_RETRYABLE_NETWORK_ERRORS = (
    'Connection aborted',
    'RemoteDisconnected',
    'Remote end closed connection',
    'ConnectionResetError',
    # RestProxy перезапускается — соединение отклонено на уровне TCP.
    'NewConnectionError',
    'Max retries exceeded',
    'Connection refused',
    'Failed to establish a new connection',
)


def login_admin():
    """
    Авторизация администратора. Возвращает (text, is_ok, token, lang).
    Токен кэшируется на _TOKEN_TTL секунд; повторные вызовы возвращают кэш без HTTP-запроса.
    При ошибке token='' и lang=''.
    """
    global _token_cache, _token_lang_cache, _token_expire
    with _token_lock:
        if _token_cache and time.time() < _token_expire:
            return '', True, _token_cache, _token_lang_cache

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
            txt = f'Other error occurred: {err}'
        else:
            try:
                txt = response.text
                result = response.ok
                if result:
                    js = json.loads(txt)
                    if "accessToken" in js:
                        token_admin = js["accessToken"]
                    if 'lang' in js:
                        lang_admin = js['lang']
                    _token_cache = token_admin
                    _token_lang_cache = lang_admin
                    _token_expire = time.time() + _TOKEN_TTL
            except Exception as err:
                txt = f'Error occurred: {err}'
        return txt, result, token_admin, lang_admin


def send_rest(mes, directive="GET", params=None, lang='', token_user=None):
    """Отправляет REST-запрос к серверу. Возвращает (text, is_ok, status_info)."""
    js = {}
    if token_user is not None:
        js['token'] = token_user
    if lang == '':
        lang = config.app_lang
    if directive == 'GET' and 'lang=' not in mes:
        if '?' in mes:
            mes = mes + '&lang=' + lang
        else:
            mes = mes + '?lang=' + lang
    else:
        js['lang'] = lang   # код языка пользователя
    if params:
        # FIX: type() is not str → isinstance
        if not isinstance(params, str):
            params = json.dumps(params, ensure_ascii=False)
        js['params'] = params  # дополнительно заданные параметры
    _MAX_RETRIES = 4
    _RETRY_DELAY = 5  # секунды между попытками (достаточно для перезапуска RestProxy)
    last_err = None
    for _attempt in range(_MAX_RETRIES + 1):
        try:
            headers = {"Accept": "application/json"}
            response = _rest_session.request(directive, config.URL + mes.replace(' ', '+'), headers=headers, json=js)
        except HTTPError as err:
            txt = f'HTTP error occurred: {err}'
            return txt, False, None
        except Exception as err:
            last_err = err
            err_str = str(err)
            # Временный обрыв соединения — повторим запрос после паузы.
            # После RemoteDisconnected сессия откроет новое соединение автоматически.
            if any(m in err_str for m in _RETRYABLE_NETWORK_ERRORS) and _attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY)
                continue
            txt = f'Other error occurred: {err}'
            return txt, False, None
        else:
            return response.text, response.ok, '<' + str(response.status_code) + '> - ' + response.reason
    txt = f'Other error occurred: {last_err}'
    return txt, False, None


def is_transient_db_error(text: str) -> bool:
    """Возвращает True если текст ошибки указывает на временную недоступность PostgreSQL."""
    return any(m in text for m in _TRANSIENT_DB_ERRORS)


def write_log_db(level, src, msg, page=None, file_name='', law_id='', td=None, write_to_db=True,
                 write_to_console=True, token=None):
    # Временная недоступность БД (рестарт PG): понижаем ❌error до предупреждения,
    # в БД не пишем (она всё равно недоступна), в консоль выводим.
    if level == '❌error' and is_transient_db_error(msg):
        level = '⚠️db-restart'
        write_to_db = False
    st_td = '' if td is None else "td=%.1f sec;" % td
    st_file_name = '' if file_name is None or file_name == '' else 'file=' + file_name + ';'
    st_law_id = '' if law_id is None or law_id == '' else 'law_id=' + str(law_id) + ';'
    st_page = '' if page is None or page == '' else 'page=' + str(page) + ';'
    if write_to_console:
        print(time.asctime(time.gmtime(time.time())) + ':', level + ';', src + ';', st_td, st_page, st_law_id,
              st_file_name.replace('\n', ' '), msg.replace('\n', ' '), flush=True)
    if not write_to_db:
        return
    if token is None:
        answer, is_ok, token, lang = login_admin()
    else:
        is_ok = True
        answer = ''
    if is_ok:
        if page is None or page == '':
            page = 'NULL'
        if law_id is None:
            law_id = ''
        if not file_name:
            file_name = get_computer_name()
        # FIX: type() == float → isinstance
        td = 'NULL' if td is None else "%.1f" % td if isinstance(td, float) else td
        st = "select {schema}.pw_logs('{level}', '{source}', %s, {page}, '{law_id}', %s, {td})".format(
                schema=config.schema_name, level=level, source=src, page=page, law_id=law_id, td=td
              )
        answer, is_ok, status = send_rest(
            'v2/execute', 'PUT', params={"script": st, "datas": (msg, file_name)}, token_user=token)
        if not is_ok:
            if '<401>' in str(status):
                invalidate_token_cache()
            print(time.ctime(), 'ERROR', 'write_log_db', str(answer), flush=True)
    else:
        print(time.ctime(), 'ERROR', 'write_log_db', str(answer), flush=True)


def load_config_params(name_function):
    """Загружает параметры конфигурации для указанной функции из БД."""
    url = "v1/select/{schema}/v_nsi_functions_params?where=name_function='{name_function}'".format(
        schema=config.schema_name, name_function=name_function)
    answer, is_ok, status_code = send_rest(url)
    if is_ok:
        return json.loads(answer)
    return []  # FIX: явный return при ошибке (вызывающие итерируют результат)


def translate_to_base(st):
    """Экранирует спецсимволы (переводы строк, скобки, кавычки и т.д.) для передачи через REST API."""
    if st is None:
        return st
    st = st.replace('\n', '~LF~').replace('(', '~A~').replace(')', '~B~').replace('@', '~a1~')
    st = st.replace(',', '~a2~').replace('=', '~a3~').replace('"', '~a4~').replace("'", '~a5~')
    st = st.replace(':', '~a6~').replace('/', '~b1~').replace('&', '~b2~').replace('\r', '~R~')
    return st


def translate_from_base(st):
    """Обратное преобразование: восстанавливает спецсимволы из экранированной строки."""
    if st is not None:
        st = st.replace('~A~', '(').replace('~B~', ')').replace('~a1~', '@').replace('~LF~', '\n')
        st = st.replace('~a2~', ',').replace('~a3~', '=').replace('~a4~', '"').replace('~a5~', "'")
        st = st.replace('~a6~', ':').replace('~b1~', '/').replace('~b2~', '&').replace('~R~', '\r')
    return st


def send_tg(st):
    """Отправляет HTML-сообщение в Telegram-канал. Возвращает ответ Telegram API."""
    token_bot, chat_id = get_param_telegram()
    url = f'https://api.telegram.org/bot{token_bot}/sendMessage'
    answer = requests.get(url, params={'chat_id': chat_id, 'text': st, 'parse_mode': 'HTML'}).json()
    return answer


def set_value_config_param(key, par, value, token_admin=None, code_function=None):
    """Записывает значение параметра конфигурации в БД."""
    if token_admin is None:
        answer, is_ok, token_admin, lang_admin = login_admin()
        if not is_ok:
            write_log_db('❌ERROR', SRC,'set_value_config_param\n' + str(answer) + '.\n Для ' +
                         par[0]['name_function'] + ' ' + key + '=' + str(value))
    else:
        ident = None
        is_number = True
        for unit in par:
            if unit['code'] == key and 'id' in unit:
                ident = unit["id"]
                is_number = unit['is_number']
                break
        if ident is None and code_function is not None:
            answer, is_ok, status_response = send_rest(
                "v1/select/{schema}/nsi_parser_functions?where=sh_name='{code_function}'".format(
                    schema=config.schema_name, code_function=code_function), params={"columns": "id"})
            if is_ok:
                ident = json.loads(answer)[0]['id']
            else:
                write_log_db('ERROR', SRC,'set_value_config_param\n' + str(answer))
        if ident is not None:
            if is_number:
                params = {"values": {"value": str(value)}}
            else:
                params = {"values": {"value": "'" + value + "'"}}
            answer, is_ok, status = send_rest(
                'v1/update/{schema}/{table}?where=id={ident}'.format(
                    schema=config.schema_name, table='nsi_functions_params', ident=ident),
                'PATCH', params=params, token_user=token_admin)
            if not is_ok:
                write_log_db(
                    '❌ERROR', SRC, 'set_value_config_param\n' + str(answer) + '.\n Для ' +
                                 par[0]['name_function'] + ' ' + key + '=' + str(value))
            else:
                return True
    return False


def st_today():
    """Возвращает текущую дату UTC в формате 'YYYY-MM-DD'."""
    return str(time.gmtime().tm_year) + '-' + str(time.gmtime().tm_mon).rjust(2, '0') + '-' + \
           str(time.gmtime().tm_mday).rjust(2, '0')


def get_web_url():
    """Возвращает базовый URL веб-интерфейса из конфигурации БД."""
    par = load_config_params('web')
    return get_value_config_param('url', par)


def check_date(txt, fmt):
    """Пытается распарсить дату txt по формату fmt. Возвращает struct_time или None."""
    # FIX: параметр 'format' затенял встроенную функцию; переименован в 'fmt'
    # FIX: bare except → except ValueError (strptime бросает ValueError при несовпадении)
    try:
        return time.strptime(txt, fmt)
    except ValueError:
        return None


def parse_russian_date(date_str):
    """Заменяет русское название месяца на английское для парсинга strptime."""
    months = {
        'январь': 'January', 'января': 'January',
        'февраль': 'February', 'февраля': 'February',
        'марта': 'March','март': 'March',
        'апрель': 'April', 'апреля': 'April',
        'май': 'May', 'мая': 'May',
        'июнь': 'June', 'июня': 'June',
        'июль': 'July', 'июля': 'July',
        'августа': 'August', 'август': 'August',
        'сентябрь': 'September', 'сентября': 'September',
        'октябрь': 'October', 'октября': 'October',
        'ноябрь': 'November', 'ноября': 'November',
        'декабрь': 'December', 'декабря': 'December'
    }

    for rus, eng in months.items():
        if rus in date_str.lower():
            return date_str.lower().replace(rus, eng)

    return date_str

def make_search(word, txt):
    """Ищет слово word в тексте txt с учётом границ слов. Возвращает количество совпадений."""
    result = 0
    if word:
        word = word.strip()
        if word:
            if word[0] == '^':
                word_s = r"\b{word}\b".format(word=word[1:-1].strip())
                matches = re.findall(word_s, txt)
            else:
                word_s = r"\b{word}\b".format(word=word)
                matches = re.findall(word_s, txt, re.IGNORECASE)
            return len(matches)  # количество вхождений в текст
    return result


def extract_text(element, default=''):
    """Извлекает текст из BeautifulSoup-элемента. Возвращает default если элемент None или пуст."""
    if element is not None:
        result = element.text
        if result:
            return result.strip()
        else:
            return default
    return default


def make_tg(source, themes, values, rss, number=0, count=0):
    """Формирует и отправляет сообщение о найденной новости в Telegram-канал."""
    global count_tg_ok, count_tg_err
    description = values['description_ru'] if 'description_ru' in values else ''
    description = html_module.unescape(translate_from_base(description))
    description = re.sub(r'<[^>]+>', '', description)                   # закрытые теги
    description = re.sub(r'</?[a-zA-Z][a-zA-Z0-9]*', '', description)  # незакрытые фрагменты вида '<p '
    if len(description) > 500:
        description = description[:500] + ' ...'
    description = html_module.escape(description)  # экранируем <, >, & чтобы не сломать Telegram HTML
    href = str(get_web_url() or '') + '/one_new/{id}'.format(id=values['id'])
    _title_raw = html_module.unescape(translate_from_base(values['title_ru']))
    _title_raw = re.sub(r'<[^>]+>', '', _title_raw)
    title = html_module.escape(re.sub(r'</?[a-zA-Z][a-zA-Z0-9]*', '', _title_raw))
    st = "<u>{rss_name}</u> ({public_date})                        [{id}]" \
         "\n[<b>{theme_name}</b>] {lang}" \
         "\n\n<b>{title}</b>" \
         "\n\n{description}\n\n<b>{href}</b>\n\n{url}".format(
            rss_name=html_module.escape(translate_from_base(rss['sh_name'])),
            public_date=values['public_date'] if 'public_date' in values else 'нет даты новости',
            theme_name=html_module.escape(str(themes)),
            title=title, lang=rss['lang'], id=values['id'],
            description=description,
            href=href, url=html_module.escape(translate_from_base(values['url']))
            )
    if 'author' in values:
        author = re.sub(r'<[^>]+>', '', html_module.unescape(str(values['author'])))
        st += '\nauthor [<b>{author}</b>]'.format(author=html_module.escape(author))
    st = st.replace('​​', '')
    ans = send_tg(st)
    if ans['ok']:
        # передача в чат прошла успешно
        # self.fixation_sent(ident, law_id, 'true')
        count_tg_ok += 1
        write_log_db(
            'info', SRC,
            '✈️ В ТЕЛЕГРАМ (Nasha_stengazeta) передана новость с ID={id} от [{rss_name} id={rss_id}] (номер={number} из {count}) по теме [{themes_name}]'.format(
                id=values['id'], rss_name=rss['sh_name'], rss_id=rss['id'], number=number + 1, count=count, themes_name=themes),
            law_id=themes + '\n' + source, page=values['file'] if 'file' in values else None)
    else:
        # ошибка передачи в чат - запишем в лог и попробуем позже
        count_tg_err += 1
        write_log_db(
            '❌ERROR', SRC,
            'make_tg\nОшибка: {ans}\n при передачи в ТЕЛЕГРАМ (Nasha_stengazeta) новости с ID={id} от [{rss_name} id={rss_id}]'.
            format(id=str(values['id']) + '\n' + st, rss_name=rss['sh_name'], ans=ans, rss_id=rss['id']),
            law_id=themes + '\n' + source)


def to_utc(dt, txt):
    """Преобразует struct_time к UTC, извлекая часовой пояс и PM-смещение из текста."""
    h = 0
    if '+' in txt:
        h = int(txt.split('+')[1][:2])
    if '-' in txt:
        h = int(txt.split('-')[1][:2])
    if 'PM' in txt:
        h += 12
    if 'p.m' in txt:
        h += 12
    dt = datetime.datetime.fromtimestamp(time.mktime(dt)) - datetime.timedelta(hours=h)
    # FIX: было "{date}".format(date=str(dt)) — двойная избыточность
    return str(dt)


def load_rss(rss_id, source):
    """Загружает описание RSS-сайта по ID из БД. Возвращает (success, rss_dict)."""
    url = f"v2/select/{config.schema_name}/nsi_rss_list?where=id={rss_id}"
    ans, is_ok, status = send_rest(url)
    if not is_ok:
        # FIX: было "\load_rss" — \l не является escape-последовательностью
        write_log_db(
            '❌error', SRC, f"Ошибка {ans} для {url}\nload_rss", law_id=source)
        return False, {}
    else:
        ans = json.loads(ans)
        if len(ans) == 1:
            return True, ans[0]
        else:
            # FIX: было "\load_rss" — \l не является escape-последовательностью
            write_log_db(
                '❌error', SRC, f"Ошибка: отсутствует RSS с ID={rss_id}\nload_rss", law_id=source)
            return False, {}


def load_list_themes(source):
    """Загружает список активных поисковых образов (тем) из БД. Возвращает (success, themes_list)."""
    url = 'v2/entity/values?app_code={schema}&object_code=rss_themes&where=stop is null or not stop'.format(
        schema=config.schema_name)
    ans, is_ok, status = send_rest(url)
    if not is_ok:
        write_log_db(
            '❌error', SRC, f"Ошибка {ans} для {url}\nload_list_themes", law_id=source)
        return False, []
    else:
        return True, json.loads(ans)


def _has_exception(data, *text_fields):
    """Возвращает True, если хотя бы один образ из поля exception найден в любом из переданных текстов."""
    exc = data.get('exception') or ''
    if not exc:
        return False
    for exc_word in exc.split(';'):
        for text in text_fields:
            if text and make_search(exc_word, text):
                return True
    return False


def seek(rss_themes, values):
    """Ищет поисковые образы в заголовках и описаниях (ru/en/he). Записывает найденные ID тем в values['themes']."""
    values['themes'] = []
    for data in rss_themes:
        words = data['value'].split(';')
        count = 0
        for word in words:
            if 'title_ru' in values:
                count += make_search(word, values['title_ru'])
            if 'title_en' in values:
                count += make_search(word, values['title_en'])
            if 'title_he' in values:
                count += make_search(word, values['title_he'])

            if 'description_ru' in values:
                count += make_search(word, values['description_ru'])
            if 'description_en' in values:
                count += make_search(word, values['description_en'])
            if 'description_he' in values:
                count += make_search(word, values['description_he'])
        if count and not _has_exception(data,
                values.get('title_ru'), values.get('title_en'), values.get('title_he'),
                values.get('description_ru'), values.get('description_en'), values.get('description_he')):
            values['themes'].append(data['id'])


def seek_article(rss_themes, values):
    """Ищет поисковые образы в полном тексте статьи (text_ru/en/he). Записывает найденные ID тем в values['themes']."""
    values['themes'] = []
    for data in rss_themes:
        words = data['value'].split(';')
        count = 0
        for word in words:
            count += make_search(word, values['text_en'])
            count += make_search(word, values['text_ru'])
            count += make_search(word, values['text_he'])
        if count and not _has_exception(data, values.get('text_en'), values.get('text_ru'), values.get('text_he')):
            values['themes'].append(data['id'])


def make_theme(theme, values, source, token):
    """Записывает связь (relation) между темой и новостью в БД."""
    param = dict()
    param['id'] = theme
    param['value'] = 1
    param['obj_id'] = values['id']
    txt = 'v1/relations/{schema}/rss_themes/rss'.format(schema=config.schema_name)
    t0 = time.time()
    ans, ok, status = send_rest(txt, 'PUT', params=param, token_user=token)
    if not ok:
        # Дублирующая связь — штатная ситуация (unique constraint), не логируем как ошибку
        if 'unique constraint' in str(ans) or 'duplicate key' in str(ans):
            return
        write_log_db('❌Error', SRC, '❗' + str(ans) + '\n' + txt, td=time.time() - t0, token=token,
                            law_id=source)


def get_name_theme(rss_themes, theme_id):
    """Возвращает краткое имя темы по её ID из списка тем."""
    result = ''
    for data in rss_themes:
        if data['id'] == int(theme_id):
            return data['sh_name']
    return result


def is_exist_object(values, token):
    """Проверяет наличие новости в БД по URL. Возвращает True/False/None(ошибка)."""
    where = "url=%s"
    ans, is_ok, status = send_rest(
        'v2/entity/values?app_code={app_code}&object_code=log_rss_history&where={where}'.format(
            app_code=config.schema_name, where=where), params={"datas": values['url']})
    if not is_ok:
        write_log_db(
            '❌error', SRC, f"is_exist_object\nОшибка {ans}\nis_exist_object", law_id='SearchRSS')
        return None
    ans = json.loads(ans)
    if len(ans) > 0:
        values['id'] = ans[0]['id']
        # уже есть в истории, но может не быть даты публикации - дополним
        if ans[0].get('public_date') is None:
            if values.get('public_date'):
                date = values.get('public_date')
            elif values.get('at_date_time'):
                date = values.get('at_date_time')
            else:
                date = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
            val = {"id": values['id'], "sh_name": '%(rss)s', "public_date": '%(public_date)s'}
            datas = {"public_date": date, "rss": values['rss']}
            params = {"schema_name": config.schema_name, "object_code": "log_rss_history", "values": val, "datas": datas}
            answer, is_ok, _ = send_rest(
                'v3/entity', 'PUT', params=params, token_user=token)
            if not is_ok:
                write_log_db(
                    '❌error', SRC, 'is_exist_object\n' + f"Ошибка обновления public_date: {answer}", law_id='SearchRSS')

    else:  # нет в логе — проверим основную таблицу
        answer, is_ok, status = send_rest(
            'v2/entity/values?app_code={app_code}&object_code=rss_history&where={where}'.format(
                app_code=config.schema_name, where=where), params={"datas": values['url']})
        if not is_ok:
            write_log_db(
                '❌error', SRC, 'is_exist_object\n' + f"Ошибка проверки rss_history: {answer}", law_id='SearchRSS')
            return None
        answer = json.loads(answer)
        if len(answer) > 0:  # уже есть в основной таблице
            values['id'] = answer[0]['id']
            fix_new(values, token)  # запишем в лог истории
            return True  # новость уже есть
    return len(ans) > 0


def fix_new(values, token):
    """Фиксирует новость в таблице истории (log_rss_history) как обработанную."""
    value = {"sh_name": "'" + str(values['rss']) + "'", "url": '%(url)s'}
    datas = {"url": values['url']}
    if values.get('public_date'):
        value["public_date"] = '%(public_date)s'
        datas["public_date"] = values['public_date']
    elif values.get('at_date_time'):
        value["public_date"] = '%(public_date)s'
        datas["public_date"] = values['at_date_time']
    else:
        value["public_date"] = '%(public_date)s'
        datas["public_date"] = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    an, is_ok, _ = send_rest(
        'v3/entity', 'PUT',
        params={"schema_name": config.schema_name, "object_code": "log_rss_history", "values": value, "datas": datas},
        token_user=token)
    if not is_ok:
        print(an)
        # при новой новости, записанной в основную таблицу, будет ошибка здесь - не страшно, зато надежно
        # if not is_ok:
        #     print(str(an))


def write_history(values, token, rss, source):
    """Записывает новость в основную таблицу rss_history. Возвращает ID записи или None при ошибке."""
    def zap(key, value, data):
        if key in values and values[key]:
            value[key] = f'%({key})s'
            data[key] = values[key]
        return data

    # Декодируем HTML-сущности (&laquo;, &raquo;, &amp; и т.п.) перед записью в БД
    for _field in ('title_ru', 'title_en', 'title_he', 'description_ru', 'description_en', 'description_he'):
        if _field in values and isinstance(values[_field], str):
            values[_field] = html_module.unescape(values[_field])

    if 'id' in values:
        values.pop('id')
    rss['count_new'] += 1
    datas = {}
    val = dict()
    datas = zap('url', val, datas)
    datas = zap('title_ru', val, datas)
    datas = zap('description_ru', val, datas)
    datas = zap('author', val, datas)
    datas = zap('title_en', val, datas)
    datas = zap('description_en', val, datas)
    datas = zap('title_he', val, datas)
    datas = zap('description_he', val, datas)
    datas = zap('meta_img', val, datas)
    datas = zap('rss', val, datas)
    datas = zap('at_date_time', val, datas)
    datas = zap('lang', val, datas)
    datas = zap('public_date', val, datas)
    if 'file' in values:
        datas = zap('file', val, datas)
    if 'error_translator' in values:
        val["error_translator"] = values['error_translator']

    params = {"schema_name": config.schema_name, "object_code": "rss_history", "values": val, "datas": datas}
    ans, is_ok, status = send_rest('v3/entity', 'PUT', params=params, token_user=token)
    if not is_ok:
        write_log_db(
            '❌error', SRC, f"write_history\nОшибка {ans}\n" + json.dumps(params, indent=4, ensure_ascii=False),
            law_id=source, token=token)
        return None  # FIX: явный return None вместо неявного (вызывающий код проверяет if ok_write:)
    else:
        values['id'] = int(json.loads(ans)[0]['id'])
        return values['id']


def get_public_date(txt):
    """Парсит дату публикации из различных текстовых форматов (включая русские месяцы, UTC, PM)."""
    if not txt:
        return txt
    # RFC 2822: "Tue, 03 Mar 2026 18:00:40 +0300" — locale-independent парсинг
    try:
        dt = email.utils.parsedate_to_datetime(txt.strip())
        dt_utc = dt.astimezone(datetime.timezone.utc)
        return dt_utc.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        pass
    txt = parse_russian_date(
        txt.strip()
        .replace(' GMT', '')
        .replace('T', ' ')
        .replace('Z', '')
        .replace(',', '')
        .replace('ue', '')
        .replace('hu', '')
        .replace('EST', '')
        .replace('ES', '').strip()
    )
    # FIX: убрана лишняя пустая строка
    formats = [
        '%a %d %b %Y %H:%M:%S %z',  # день недели число месяц год час минута секунда UTC
        '%a, %d %b %Y %H:%M:%S %z', # день недели, число месяц год час минута секунда UTC
        '%a %d %b %Y %H:%M:%S',     # день недели число месяц год час минута секунда
        '%d %b %Y %H:%M:%S %z',     # число месяц год час минута секунда UTC
        '%d %b %Y %H:%M:%S',        # число месяц год час минута секунда
        '%B %d %Y %H:%M PM',        # месяц число год час минута PM
        '%B %d %Y %H:%M p.m',       # месяц число год час минута p.m
        '%d %B %Y %H:%M',           # день месяц год час минута
        '%B %d %Y %H:%M AM',        # месяц число год час минута AM
        '%B %d %Y %H:%M'            # месяц число год час минута
    ]

    for fmt in formats:
        dt = check_date(txt, fmt)
        if dt:
            return to_utc(dt, txt) if '%z' in fmt or 'PM' in fmt or 'p.m' in fmt else time.strftime('%Y-%m-%d %H:%M:%S', dt)
    return txt
