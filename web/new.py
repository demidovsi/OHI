import json
import time

from flask import flash
import openai

import config
import common
import cloud
from common import add, get
import article_parser

array_default = [
    {'key': 'scroll', 'value': 0},
    {'key': 'page_for_return', 'value': 0},
    {'key': 'unit', 'value': {}},
    {'key': 'select_lang', 'value': 'ru'},
    {'key': 'languages', 'value': ['ru', 'en', 'he']},
]

api_key = 'w5TDjcKQwrTDhcOHwpTCrMKxwprDjsKywq3CssKXw43CssOXw5XCscORwqrCvMK4wpTCpMOPw4bDjMKowq3CrsKrwpPCpMKxwrXCq8ORwpXCuMONwrfCq8OLwqvCqsKZwqzDk8Kk'


def load_inform(answer):
    answer['unit'] = dict()
    ans, is_ok, status = common.send_rest(
        'v2/entity/values?app_code={schema}&object_code=rss_history&object_id={id}'.format(
            schema=config.SCHEMA, id=answer['new_id']))
    if not is_ok:
        flash(str(ans), 'warning')
        return False
    else:
        unit = json.loads(ans)[0]
        if unit['public_date']:
            unit['public_date'] = unit['public_date'].replace('T', ' ')
        unit['title_ru_init'] = unit['title_ru']
        unit['title_en_init'] = unit['title_en']
        unit['title_he_init'] = unit['title_he']
        unit['description_ru'] = unit['description_ru'] if unit['description_ru'] else ''
        unit['description_en'] = unit['description_en'] if unit['description_en'] else ''
        unit['description_he'] = unit['description_he'] if unit['description_he'] else ''
        unit['description_ru_init'] = unit['description_ru']
        unit['description_en_init'] = unit['description_en']
        unit['description_he_init'] = unit['description_he']

        ans, is_ok, status = common.send_rest('v2/select/{schema}/get_list_theme_for_history?where=id={new_id}'.format(
            schema=config.SCHEMA, new_id=answer['new_id']))
        if not is_ok:
            flash(str(ans), 'warning')
        else:
            ans = json.loads(ans)
            unit['name_theme'] = ''
            for data in ans:
                unit['name_theme'] = unit['name_theme'] + ', ' if unit['name_theme'] else unit['name_theme']
                unit['name_theme'] += data['sh_name']
        answer['unit'] = unit
        return True


def make_info(user_id, answer):
    lang = answer['select_lang']
    answer['unit']['title'] = answer['unit']['title_' + lang]
    answer['unit']['title_init'] = answer['unit']['title_' + lang + '_init']

    answer['unit']['description'] = answer['unit']['description_'+lang]
    answer['unit']['description_init'] = answer['unit']['description_'+lang + '_init']

    if answer['unit']['file']:
        if 'full_' + lang not in answer['unit']:
            answer['unit']['full_' + lang] = cloud.load_file(user_id, lang + '_' + str(answer['unit']['id']))
            answer['unit']['full_' + lang + '_init'] = answer['unit']['full_' + lang]
        answer['unit']['full'] = answer['unit']['full_'+lang]
        answer['unit']['full_init'] = answer['unit']['full_' + lang + '_init']


def refresh(answer):
    def slave(key):
        if key + '_init' in answer['unit']:
            answer['unit'][key] = answer['unit'][key + '_init']

    slave('title_ru')
    slave('title_en')
    slave('title_he')
    slave('title')
    slave('description_ru')
    slave('description_en')
    slave('description_he')
    slave('description')
    slave('full_ru')
    slave('full_en')
    slave('full_he')
    slave('full')


def define_from_form(request, answer):
    lang = answer['select_lang']
    answer['unit']['title_' + lang] = request.form.get('title')
    answer['unit']['title'] = request.form.get('title')

    answer['unit']['description_' + lang] = request.form.get('description')
    answer['unit']['description'] = request.form.get('description')

    answer['unit']['full_' + lang] = request.form.get('full')
    answer['unit']['full'] = request.form.get('full')


def save(user_id, answer):
    id = int(answer['new_id'])
    values = dict()
    values['id'] = id
    lang = answer['select_lang']
    params = {"schema_name": config.SCHEMA, "object_code": "rss_history", "values": values}
    values["title" + '_' + lang] = answer['unit']['title']
    values["description" + '_' + lang] = answer['unit']['description']
    if lang == answer['unit']['lang']:
        values['file'] = len(answer['unit']['full'])

    ans, is_ok, status = common.send_rest('v2/entity', 'PUT', params=params, token_user=get(user_id, 'token'))
    if not is_ok:
        flash(str(ans), 'warning')
    else:
        diff = common.what_change(
            {'title': answer['unit'].get('title_' + lang + '_init'),
             'description': answer['unit'].get('description_' + lang + '_init')},
            {'title': answer['unit']['title_' + lang],
             'description': answer['unit']['description_' + lang]})
        common.write_log_db('Сохранение новости', 'new', diff, law_id=str(id), page=id,
                        file_name=get(user_id, 'user_address'))
        answer['unit']['title_' + lang + '_init'] = answer['unit']['title_' + lang]
        answer['unit']['description_' + lang + '_init'] = answer['unit']['description_' + lang]
        if 'file' in values:
            answer['unit']['file'] = values['file']
    filename = answer['select_lang'] + '_' + str(answer['unit']['id']) + '.txt'
    cloud.save_file_bucket(filename, answer['unit']['full'])
    if 'full_' + lang in answer['unit']:
        answer['unit'].pop('full_' + lang, None)  # удалить, если есть, чтобы не мешало


def need_article(user_id, answer):
    new_id = answer['new_id']
    try:
        article = article_parser.extract_ynet_article(answer['unit']['url'])
        # Разбор HTML - эвристика (JSON-LD/DOM fallback у article_parser), не
        # гарантирует результат на каждом сайте: если ничего не нашлось, поля
        # приходят пустыми строками БЕЗ исключения - без проверки они молча
        # перетирали бы уже введённый текст в title/description (два левых
        # textarea на форме).
        if not (article.get('title') or article.get('subtitle') or article.get('text')):
            flash('Не удалось распознать содержимое статьи на странице', 'warning')
            common.write_log_db('Обновление статьи с сайта', 'new',
                            'Не удалось распознать содержимое: ' + str(answer['unit']['url']),
                            law_id=str(new_id), page=new_id, file_name=get(user_id, 'user_address'))
            return
        answer['select_lang'] = article['lang'] if article['lang'] in answer['languages'] else 'ru'
        if article.get('title'):
            answer['new_title'] = article['title']
        if article.get('subtitle'):
            answer['new_description'] = article['subtitle']
        if article.get('text'):
            answer['new_full'] = article['text']
            answer['unit']['file'] = len(answer['new_full'])
        common.write_log_db('Обновление статьи с сайта', 'new',
                        'Заново прочитана статья: ' + str(answer['unit']['url']),
                        law_id=str(new_id), page=new_id, file_name=get(user_id, 'user_address'))
    except Exception as err:
        if '410 Client Error' in str(err):
            flash('Страница удалена (410)', 'warning')
        else:
            flash('Ошибка получения статьи: ' + str(err), 'warning')
        common.write_log_db('Обновление статьи с сайта', 'new',
                        'Ошибка получения статьи (' + str(answer['unit']['url']) + '): ' + str(err)[:200],
                        law_id=str(new_id), page=new_id, file_name=get(user_id, 'user_address'))


def prepare_form(user_id, request, new_id):
    answer = dict()
    st = common.init_form(user_id, request, '/news_board/')
    if st:
        answer['redirect'] = st
        return answer
    common.default_form(user_id, array_default, answer, 'one_new_')
    answer['new_id'] = new_id
    if request.method == 'POST':
        # 'one_new_unit' в сессии - один слот на пользователя, а не на
        # конкретную новость. Если между открытием ЭТОЙ статьи и текущим
        # запросом успел выполниться запрос для ДРУГОЙ (несколько вкладок/
        # модалок, гонка запросов), в сессии может лежать unit чужой новости -
        # тогда перевод/сохранение ушли бы не в ту запись, а текст в форме
        # выглядел бы "с чужой новости". При несовпадении id принудительно
        # перечитываем нужную статью из БД, прежде чем применять форму.
        if str(answer['unit'].get('id')) != str(new_id):
            load_inform(answer)
        common.choose_language(user_id, request)
        if 'back' in request.form:
            answer['redirect'] = answer['page_for_return']
            add(user_id, 'page_for_return', '')
            add(user_id, 'text_for_return', '')
            return answer
        define_from_form(request, answer)
        if 'select_lang' in request.form:
            new_select_lang = request.form.get('select_lang')
            if new_select_lang != answer['select_lang']:
                common.write_log_db('Смена языка вывода', 'new',
                                'Язык вывода: {old} -> {new}'.format(
                                    old=answer['select_lang'], new=new_select_lang),
                                law_id=str(new_id), page=new_id, file_name=get(user_id, 'user_address'))
            answer['select_lang'] = new_select_lang
        if 'refresh' in request.form:
            refresh(answer)
            common.write_log_db('Отмена изменений', 'new', 'Отменены несохранённые изменения',
                            law_id=str(new_id), page=new_id, file_name=get(user_id, 'user_address'))
        if 'save' in request.form:
            save(user_id, answer)
        if 'translate_ru' in request.form:
            make_translate(user_id, 'Перевести на русский', answer, 'ru')
        if 'translate_en' in request.form:
            make_translate(user_id, 'Перевести на английский', answer, 'en')
        if 'translate_he' in request.form:
            make_translate(user_id, 'Translate to Hebrew', answer, 'he')
        if 'need_article' in request.form:
            need_article(user_id, answer)
    else:
        answer['select_lang'] = 'ru'
        common.write_log('Содержимое новости', user_id, request, page=new_id)
        load_inform(answer)
        # Открытие статьи прямой ссылкой (например, из news_board.js) не
        # проходит через news.py:check_show, который обычно выставляет эти
        # ключи перед переходом сюда - без них кнопка "Назад" не показывалась
        # бы вовсе (see templates/new.html: {% if par['page_for_return'] %}).
        if request.args.get('back_to') == 'news_board':
            # select_id - чтобы news_board.js при возврате выделил фоном
            # именно ту новость, которую пользователь открыл (см. nb-row-return в
            # static/css/news_board.css и applyReturnHighlight в news_board.js)
            add(user_id, 'page_for_return', '/news_board/{user_id}/?select_id={new_id}'.format(
                user_id=user_id, new_id=new_id))
            add(user_id, 'text_for_return', 13)

    make_info(user_id, answer)
    if 'load_file' in request.form:
        filename = answer['unit']['lang'] + '_' + str(new_id) + '.txt'
        answer['unit']['full'] = cloud.load_file(user_id, filename)
        common.write_log_db('Загрузка файла в исходном языке', 'new', 'Файл: ' + filename,
                        law_id=str(new_id), page=new_id, file_name=get(user_id, 'user_address'))

    if 'new_title' in answer:
        answer['unit']['title'] = answer['new_title']
    if 'new_description' in answer:
        answer['unit']['description'] = answer['new_description']
    if 'new_full' in answer:
        answer['unit']['full'] = answer['new_full']

    answer['page_for_return'] = get(user_id, 'page_for_return')
    answer['text_for_return'] = get(user_id, 'text_for_return')
    # для возврата в форму из других форм
    common.save_form(user_id, array_default, answer, 'one_new_')
    return answer


def make_translate(user_id, question, answer, to_lang='ru'):
    """
    Функция для создания запроса на перевод текста с использованием OpenAI API.
    :param user_id: ID пользователя, для которого выполняется перевод.
    :param question: Вопрос или запрос к модели.
    :param answer: Словарь, содержащий текст для перевода.
    :param to_lang: Язык, на который нужно перевести текст (по умолчанию 'ru').
    """
    unit = answer['unit']
    values = {"id": int(answer['new_id'])}
    params = {"schema_name": config.SCHEMA, "object_code": "rss_history", "values": values}
    failed = False
    if 'description' in unit:
        content = unit['description_' + unit['lang']] if unit['lang'] else unit['description_he']
        if content:
            is_ok, text = translate(user_id, question, content, unit['id'])
            if is_ok:
                values['description_' + to_lang] = text
            else:
                failed = True
    if 'title' in unit:
        content = unit['title_' + unit['lang']] if unit['lang'] else unit['title_he']
        if content:
            is_ok, text = translate(user_id, question, content, unit['id'])
            if is_ok:
                values['title_' + to_lang] = text
            else:
                failed = True

    lang = unit['lang'] if unit['lang'] else 'he'
    content = cloud.load_file(user_id, lang + '_' + str(unit['id']))
    if content:
        is_ok, text = translate(user_id, question, content, unit['id'])
        if is_ok:
            cloud.save_file_bucket(to_lang + '_' + str(unit['id']), text)
            unit['full_' + to_lang] = text
        else:
            failed = True

    if failed:
        flash('ChatGPT не смог перевести часть текста (например, отказался из-за содержимого) - '
              'эта часть оставлена без изменений', 'warning')

    ans, is_ok, status = common.send_rest('v2/entity', 'PUT', params=params, token_user=get(user_id, 'token'))
    if not is_ok:
        flash(str(ans), 'warning')
    else:
        load_inform(answer)


REFUSAL_MARKERS = (
    'извините, я не могу', 'извините, но я не могу', 'я не могу помочь',
    'к сожалению, я не могу',
    "i'm sorry, but i can't", "i'm sorry, i can't", "i cannot assist",
    "i can't assist", "i'm unable to help", "sorry, i can't help",
    "i cannot help", "i can't help with that",
)


def _looks_like_refusal(text):
    """ChatGPT иногда отказывается выполнять перевод (например, из-за
    содержимого новости - война, насилие и т.п. под фильтрами модерации) и
    возвращает текст отказа вместо перевода - без проверки он сохранялся бы
    в БД как будто это и есть перевод, портя заголовок/описание/текст
    статьи."""
    if not text:
        return True
    low = text.strip().lower()
    return any(low.startswith(m) for m in REFUSAL_MARKERS)


def translate(user_id, question, content, message_id):
    t0 = time.time()
    try:
        openai.api_key = common.decode('abcd', api_key)
        messages = list()
        messages.append({"role": "user", "content": question})
        messages.append({"role": "user", "content": content})
        response = openai.ChatCompletion.create(
            model='gpt-4o', messages=messages,
            max_tokens=4000,
            temperature=1,
            presence_penalty=0,
            frequency_penalty=0
        )
        result = response.choices[0].message.content.strip()
        if _looks_like_refusal(result):
            common.write_log_db('ChatGPT-Exception', 'ohi_web',
                            'ChatGPT отказался выполнить перевод (' + question + '): ' + result[:200],
                            law_id=message_id, td=time.time() - t0,
                            file_name=get(user_id, 'user_address'))
            return False, result
        common.write_log_db('ChatGPT', 'ohi_web', 'Обращение к ChatGPT от пользователя: ' + question,
                        law_id=message_id, td=time.time() - t0,
                        file_name=get(user_id, 'user_address'))
        return True, result
    except Exception as er:
        common.write_log_db('ChatGPT-Exception', 'ohi_web', 'Ошибка обращения к ChatGPT от пользователя ('
                        + question + '): ' + f"{er}"[:200], law_id=message_id, td=time.time() - t0,
                        file_name=get(user_id, 'user_address'))
        return False, f"{er}"

