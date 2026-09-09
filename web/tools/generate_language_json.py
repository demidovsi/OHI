"""
Предварительная генерация полного web/static/language.json.

Переводит ВСЕ строки из ВСЕХ форм (language.py: ALL_FORMS) на ВСЕ языки из
config.languages - чтобы файл, попадающий в докер-образ (web/Dockerfile:
COPY web/ .), уже содержал полный набор переводов на момент деплоя.

Без этого прогрева на проде такой сценарий приводил к настоящим потерям:
процесс стартует с пустым language.lang (в память он подгружается только
внутри login.py/one_new - см. комментарий в main_ohi_web.py), первый
запрос к какой-либо форме на непривычном языке уходит за GoogleTranslator,
а сразу следующий save_lang() перезаписывает ВЕСЬ файл на диске тем, что
успело накопиться в памяти ТОЛЬКО в этом процессе - теряя все остальные
формы/языки, которые были в файле на момент старта.

Запуск (из директории web/, с активным venv и настроенным .env - как для
самого приложения, читает те же переменные окружения через config.py):

    cd web
    python tools/generate_language_json.py

Идемпотентен: уже переведённые строки повторно не запрашиваются у
GoogleTranslator (см. language.py: get_value_language - дозаполняет только
недостающий "хвост" каждого массива). Можно гонять после каждого
добавления/изменения строк в language.py и коммитить обновлённый
web/static/language.json вместе с остальными изменениями.
"""
import os
import sys

# language.py читает/пишет 'static/language.json' относительным путём (от
# текущей рабочей директории, как и сам web/main_ohi_web.py при запуске) -
# независимо от того, откуда фактически вызван этот скрипт, переходим в
# директорию web/ (на уровень выше tools/).
WEB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(WEB_DIR)
sys.path.insert(0, WEB_DIR)

import config
import language


def main():
    language.load_lang()

    lang_keys = [item['key'] for item in config.languages]
    if 'ru' not in lang_keys:
        lang_keys.append('ru')

    total = len(lang_keys) * len(language.ALL_FORMS)
    done = 0
    for lang_key in lang_keys:
        for form_name, array in language.ALL_FORMS.items():
            done += 1
            before = len(language.lang.get(lang_key, {}).get(form_name, []))
            language.get_value_language(form_name, array, lang_key)
            after = len(language.lang.get(lang_key, {}).get(form_name, []))
            mark = '+' if after != before else '='
            print('[{done}/{total}] {lang}/{form}: {before} -> {after} ({mark})'.format(
                done=done, total=total, lang=lang_key, form=form_name,
                before=before, after=after, mark=mark))

    print('Готово: static/language.json обновлён ({path}).'.format(
        path=os.path.abspath('static/language.json')))


if __name__ == '__main__':
    main()
