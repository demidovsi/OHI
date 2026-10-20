import json
import time

from flask import flash
import openai

import config
import common
import cloud
from common import get
import article_parser

array_default = [
    {'key': 'scroll', 'value': 0},
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


def make_info(answer):
    lang = answer['select_lang']
    answer['unit']['title'] = answer['unit']['title_' + lang]
    answer['unit']['title_init'] = answer['unit']['title_' + lang + '_init']

    answer['unit']['description'] = answer['unit']['description_'+lang]
    answer['unit']['description_init'] = answer['unit']['description_'+lang + '_init']

    if answer['unit']['file']:
        if 'full_' + lang not in answer['unit']:
            answer['unit']['full_' + lang] = cloud.load_file(lang + '_' + str(answer['unit']['id']))
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


def save(answer):
    id = int(answer['new_id'])
    values = dict()
    values['id'] = id
    lang = answer['select_lang']
    params = {"schema_name": config.SCHEMA, "object_code": "rss_history", "values": values}
    values["title" + '_' + lang] = answer['unit']['title']
    values["description" + '_' + lang] = answer['unit']['description']
    if lang == answer['unit']['lang']:
        values['file'] = len(answer['unit']['full'])

    ans, is_ok, status = common.send_rest('v2/entity', 'PUT', params=params, token_user=get('token'))
    if not is_ok:
        flash(str(ans), 'warning')
    else:
        diff = common.what_change(
            {'title': answer['unit'].get('title_' + lang + '_init'),
             'description': answer['unit'].get('description_' + lang + '_init')},
            {'title': answer['unit']['title_' + lang],
             'description': answer['unit']['description_' + lang]})
        common.write_log_db('Сохранение новости', 'new', diff, law_id=str(id), page=id)
        answer['unit']['title_' + lang + '_init'] = answer['unit']['title_' + lang]
        answer['unit']['description_' + lang + '_init'] = answer['unit']['description_' + lang]
        if 'file' in values:
            answer['unit']['file'] = values['file']
    filename = answer['select_lang'] + '_' + str(answer['unit']['id']) + '.txt'
    cloud.save_file_bucket(filename, answer['unit']['full'])
    if 'full_' + lang in answer['unit']:
        answer['unit'].pop('full_' + lang, None)  # удалить, если есть, чтобы не мешало


def need_article(answer):
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
                            law_id=str(new_id), page=new_id)
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
                        law_id=str(new_id), page=new_id)
    except Exception as err:
        if '410 Client Error' in str(err):
            flash('Страница удалена (410)', 'warning')
        else:
            flash('Ошибка получения статьи: ' + str(err), 'warning')
        common.write_log_db('Обновление статьи с сайта', 'new',
                        'Ошибка получения статьи (' + str(answer['unit']['url']) + '): ' + str(err)[:200],
                        law_id=str(new_id), page=new_id)


def prepare_form(request):
    """Карточка новости (модальное окно ленты новостей). Поля: new_id; open (открытие — читать из БД); select_lang,
    title, description, full (текст формы); действия: refresh, save, translate_ru/en/he, need_article, load_file
    (изменять — только администратор)."""
    answer = dict()
    st = common.init_form(request, '/news_board/')
    if st:
        answer['redirect'] = st
        return answer
    new_id = common.sql_digits(request.values.get('new_id'))
    if not new_id:
        answer['error'] = 'new_id'
        return answer
    common.default_form(array_default, answer, 'one_new_')
    answer['new_id'] = new_id
    admin = common.is_admin()
    actions = ('refresh', 'save', 'translate_ru', 'translate_en', 'translate_he', 'need_article', 'load_file')
    # open — открытие новости (перечитать из БД); иначе действие над новостью, уже лежащей в сессии
    if request.method == 'POST' and 'open' not in request.form and str(answer['unit'].get('id')) == str(new_id):
        common.choose_language(request)
        if admin:
            define_from_form(request, answer)
        if 'select_lang' in request.form:
            new_select_lang = request.form.get('select_lang')
            if new_select_lang in answer['languages'] and new_select_lang != answer['select_lang']:
                common.write_log_db('Смена языка вывода', 'new',
                                    'Язык вывода: {old} -> {new}'.format(
                                        old=answer['select_lang'], new=new_select_lang),
                                    law_id=str(new_id), page=new_id)
                answer['select_lang'] = new_select_lang
        if any(a in request.form for a in actions) and not admin:
            flash('Изменять новость может только администратор', 'warning')
        elif 'refresh' in request.form:
            refresh(answer)
            common.write_log_db('Отмена изменений', 'new', 'Отменены несохранённые изменения',
                                law_id=str(new_id), page=new_id)
        elif 'save' in request.form:
            save(answer)
        elif 'translate_ru' in request.form:
            make_translate('Перевести на русский', answer, 'ru')
        elif 'translate_en' in request.form:
            make_translate('Перевести на английский', answer, 'en')
        elif 'translate_he' in request.form:
            make_translate('Translate to Hebrew', answer, 'he')
        elif 'need_article' in request.form:
            need_article(answer)
    else:
        # первое открытие новости (или в сессии лежит другая новость — несколько вкладок): читаем из БД
        answer['select_lang'] = request.values.get('select_lang') if request.values.get('select_lang') in             answer['languages'] else 'ru'
        common.write_log('Содержимое новости', request, page=new_id)
        if not load_inform(answer):
            return answer

    make_info(answer)
    if 'load_file' in request.form and admin:
        filename = answer['unit']['lang'] + '_' + str(new_id) + '.txt'
        answer['unit']['full'] = cloud.load_file(filename)
        common.write_log_db('Загрузка файла в исходном языке', 'new', 'Файл: ' + filename,
                            law_id=str(new_id), page=new_id)

    if 'new_title' in answer:
        answer['unit']['title'] = answer.pop('new_title')
    if 'new_description' in answer:
        answer['unit']['description'] = answer.pop('new_description')
    if 'new_full' in answer:
        answer['unit']['full'] = answer.pop('new_full')

    common.save_form(array_default, answer, 'one_new_')
    answer['admin'] = admin
    return answer


def make_translate(question, answer, to_lang='ru'):
    """
    Функция для создания запроса на перевод текста с использованием OpenAI API.
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
            is_ok, text = translate(question, content, unit['id'])
            if is_ok:
                values['description_' + to_lang] = text
            else:
                failed = True
    if 'title' in unit:
        content = unit['title_' + unit['lang']] if unit['lang'] else unit['title_he']
        if content:
            is_ok, text = translate(question, content, unit['id'])
            if is_ok:
                values['title_' + to_lang] = text
            else:
                failed = True

    lang = unit['lang'] if unit['lang'] else 'he'
    content = cloud.load_file(lang + '_' + str(unit['id']))
    if content:
        is_ok, text = translate(question, content, unit['id'])
        if is_ok:
            cloud.save_file_bucket(to_lang + '_' + str(unit['id']), text)
            unit['full_' + to_lang] = text
        else:
            failed = True

    if failed:
        flash('ChatGPT не смог перевести часть текста (например, отказался из-за содержимого) - '
              'эта часть оставлена без изменений', 'warning')

    ans, is_ok, status = common.send_rest('v2/entity', 'PUT', params=params, token_user=get('token'))
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


def translate(question, content, message_id):
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
                            law_id=message_id, td=time.time() - t0)
            return False, result
        common.write_log_db('ChatGPT', 'ohi_web', 'Обращение к ChatGPT от пользователя: ' + question,
                        law_id=message_id, td=time.time() - t0)
        return True, result
    except Exception as er:
        common.write_log_db('ChatGPT-Exception', 'ohi_web', 'Ошибка обращения к ChatGPT от пользователя ('
                        + question + '): ' + f"{er}"[:200], law_id=message_id, td=time.time() - t0)
        return False, f"{er}"

