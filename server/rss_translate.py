"""
Поток трансляции (перевода) статей новостей.

Для новостей, у которых отсутствует перевод текста статьи, загружает текст
из облака, переводит на три языка (ru/en/he) и записывает обратно.
"""
import trafaret_thread
import common
from common import SRC
import config
import py7zr
import time
import os
import json
import shutil

import cloud
import translate

bucket_name = 'llm_news'


def get_array_text(text, limit=2000):
    """Разбивает текст на части не более limit символов, разрезая по точкам."""
    if len(text) <= limit:
        return [text]
    result = []
    while len(text) > 0:
        if len(text) <= limit:
            result.append(text)
            break
        st = text[:limit]
        # Ищем последнюю точку в чанке для аккуратного разреза
        i = len(st) - 1
        while i > 0 and st[i] != '.':
            i -= 1
        if i == 0:
            # FIX: точка не найдена — режем по limit, иначе цикл O(n²)
            result.append(st)
            text = text[limit:]
        else:
            result.append(st[:i + 1])
            text = text[i + 1:]
    return result


def load_file_bucket(filename):
    """
    Загружает текстовый файл из облачного бакета (txt или 7z).
    Возвращает (текст, True) при успехе или (сообщение_об_ошибке, False) при неудаче.
    """
    try:
        filename = str(filename)
        temp_dir = common.current_path + '/news'
        if not os.path.exists(temp_dir + '/' + filename):
            os.makedirs(temp_dir, exist_ok=True)
            file_name = os.path.splitext(filename)[0] + '.txt'
            if cloud.check_exist_blob(file_name):
                blob = cloud.get_bucket().blob(file_name)
                blob.download_to_filename(temp_dir + '/' + file_name)
            else:
                file_name = os.path.splitext(filename)[0] + '.7z'
                if cloud.check_exist_blob(file_name):
                    blob = cloud.get_bucket().blob(file_name)
                    blob.download_to_filename(temp_dir + '/' + file_name)
                    with py7zr.SevenZipFile(temp_dir + '/' + file_name, 'r') as arch:
                        arch.extractall(path=temp_dir)
                    os.remove(temp_dir + '/' + file_name)
                else:
                    # FIX: было return '' — одно значение вместо кортежа!
                    # Вызывающий код: txt, is_ok = load_file_bucket(...)
                    # → ValueError: not enough values to unpack
                    return f'Файл {filename} отсутствует в облаке', False
            filepath = temp_dir + '/' + filename + '.txt'
            if not os.path.exists(filepath):
                filepath = temp_dir + '/' + filename
            # FIX: было f = open(...); with f: — антипаттерн
            with open(filepath, 'r', encoding='utf-8') as f:
                txt = f.read()
            os.remove(filepath)
            shutil.rmtree(common.current_path + '/news/', ignore_errors=True)
            return txt, True
    except Exception as er:
        # FIX: было filename if filename is not None else 'None' + '"в облаке...'
        # Из-за приоритета операций: 'None' + '...' конкатенируется первым,
        # а str(filename) на строке выше гарантирует, что filename никогда не None.
        txt = f'ERROR: {er} файл "{filename}" в облаке недоступен или отсутствует'
        return txt, False


class TranslateRSS(trafaret_thread.TrafaretThread):
    """
    Поток перевода статей из RSS-ленты.

    Загружает список статей без перевода, для каждой:
    1. Скачивает текст из облака (GCS)
    2. Переводит тело статьи на ru/en/he
    3. Переводит заголовок и описание
    4. Сохраняет результат обратно в облако и БД
    """
    def __init__(self, source, code_function, code_period, description):
        super(TranslateRSS, self).__init__(source, code_function, code_period, description)
        self.list_complete = []  # список статей, требующих перевода
        self.global_count = 0   # общее кол-во статей в очереди
        self.global_new = 0     # кол-во успешно переведённых
        self.global_error = 0   # кол-во ошибок
        self.last_length = 0    # длина последнего обработанного текста
        self.limit = 0          # лимит символов для разбиения текста

    def initiation_parameters(self):
        super(TranslateRSS, self).initiation_parameters()
        self.par.append({"code": "period", "value": 10})
        self.par.append({"code": "active", "value": 1})
        self.par.append({"code": "limit", "value": 5000})

    def load_list_translate(self):
        """Загружает из БД список статей, у которых перевод ещё не выполнен."""
        self.list_complete = []  # освобождаем старые данные перед загрузкой
        where = 'error_translator'
        ans, is_ok, status = common.send_rest(
            'v2/entity/values?app_code={app_code}&object_code=rss_history&where={where}&column_order=id'.format(
                app_code=config.schema_name, where=where))
        if not is_ok:
            common.write_log_db(
                '❌error', SRC, f"load_list_translator\nОшибка: {ans}", law_id=self.source)
            return False
        self.list_complete = json.loads(ans)
        # FIX: было len(ans) — длина сырой JSON-строки (всегда > 0 для "[]")
        return len(self.list_complete) > 0

    def make_translate(self, values):
        """
        Переводит одну статью на три языка (ru/en/he).
        Возвращает (True, '') при успехе или (False, описание_ошибки) при неудаче.
        """
        lang = values['lang'] if values['lang'] else 'he'
        # FIX: было `values['lang'] if values['lang'] else 'iw'`
        # Если values['lang'] == 'he', lang_iw оставалось 'he', а Google Translate
        # использует 'iw' для иврита. Теперь маппинг корректен для любого значения.
        lang_iw = 'iw' if lang == 'he' else lang
        txt, is_ok = load_file_bucket(lang + '_' + str(values['id']))
        if not is_ok:
            return False, txt
        self.last_length = len(txt)
        text = get_array_text(txt, self.limit)
        text_ru = ''
        text_en = ''
        text_he = ''
        error_translator = False
        for unit in text:  # Перевод текста на три языка
            if values['lang'] != 'ru':
                try:
                    is_ok, res = translate.translator.translate(unit, 'ru')
                    # res = GoogleTranslator(target='ru').translate(unit)
                    if is_ok:
                        text_ru += res
                    else:
                        text_ru += unit
                        error_translator = True
                except Exception as er:
                    return False, er
            if values['lang'] != 'en':
                try:
                    # res = GoogleTranslator(target='en').translate(unit)
                    is_ok, res = translate.translator.translate(unit, 'en')
                    if is_ok:
                        text_en += res
                    else:
                        error_translator = True
                        text_en += unit
                except Exception as er:
                    return False, er
            if values['lang'] != 'he':
                try:
                    is_ok, res = translate.translator.translate(unit, 'iw')
                    # res = GoogleTranslator(target='iw').translate(unit)
                    if is_ok:
                        text_he += res
                    else:
                        error_translator = True
                        text_he += unit
                except Exception as er:
                    return False, er

        if not error_translator:
            # Сохраняем переведённые тексты в облако
            if values['lang'] != 'ru':
                cloud.save_file_bucket('ru_' + str(values['id']), text_ru)
            if values['lang'] != 'en':
                cloud.save_file_bucket('en_' + str(values['id']), text_en)
            if values['lang'] != 'he':
                cloud.save_file_bucket('he_' + str(values['id']), text_he)

            # Переводим заголовок и описание, формируем запрос на обновление БД
            datas = {}
            value = {"id": values['id']}
            # заголовок новости
            txt = values['title_' + lang]
            if txt:
                error_t, value['title_ru'], value['title_en'], value['title_he'] = translate.make_translate(txt, lang_iw)
                datas['title_ru'] = value['title_ru']
                datas['title_en'] = value['title_en']
                datas['title_he'] = value['title_he']
                value['title_ru'] = '%(title_ru)s'
                value['title_en'] = '%(title_en)s'
                value['title_he'] = '%(title_he)s'
            else:
                error_t = False

            # текст новости
            txt = values['description_' + lang]
            if txt:
                error, value['description_ru'], value['description_en'], value['description_he'] = (
                    translate.make_translate(txt, lang_iw))
                datas['description_ru'] = value['description_ru']
                datas['description_en'] = value['description_en']
                datas['description_he'] = value['description_he']
                value['description_ru'] = '%(description_ru)s'
                value['description_en'] = '%(description_en)s'
                value['description_he'] = '%(description_he)s'
            else:
                error = False

            value["error_translator"] = error_t or error

            params = {"schema_name": config.schema_name, "object_code": "rss_history",
                      "values": value, "datas": datas}
            ans, is_ok, status = common.send_rest('v3/entity', 'PUT', params=params, token_user=self.token)
            if not is_ok:
                common.write_log_db(
                    '❌error', SRC, f"make_translate\nОшибка: {ans}\n id={values['id']}", law_id=self.source)
            return True, ''
        else:
            return False, 'Ошибка перевода'

    def work(self):
        super(TranslateRSS, self).work()
        if self.load_list_translate() and self.make_login():
            self.limit = common.get_value_config_param('limit', self.par)
            self.global_count = len(self.list_complete)
            self.global_error = 0
            self.global_new = 0
            for j, data in enumerate(self.list_complete):
                t0 = time.time()
                try:
                    is_ok, er = self.make_translate(data)
                    if not is_ok:
                        self.global_error += 1
                        common.write_log_db(
                            '⚠️warning', SRC, f"Ошибка: {er}\n id={data['id']}", law_id=self.source, page=j+1, td=time.time() - t0)
                    else:
                        # FIX: global_new не инкрементировался при успехе
                        self.global_new += 1
                        common.write_log_db(
                            '✔️translate', SRC, f"Трансляция статьи завершена\n id={data['id']}",
                            law_id=self.source, page=j+1, td=time.time() - t0)
                except Exception as er:
                    self.global_error += 1
                    common.write_log_db(
                        '❌error', SRC, f"work\nОшибка: {er}\n id={data['id']}", law_id=self.source, page=j+1, td=time.time() - t0)
            self.list_complete = []  # освобождаем список после обработки
            self.finish_text += 'Трансляция статей новостей:\nВсего пропусков={global_count}\n' \
                                'Добавлено={global_new}\nОшибок={global_error}'.format(
                global_count=self.global_count, global_error=self.global_error, global_new=self.global_new)
            return True


if __name__ == "__main__":
    common.current_path = os.path.abspath(os.curdir)
    TranslateRSS('TranslateRSS', 'TranslateRSS', 'period', 'Поток "Трансляция статей новостей" загружен').start()

    while True:
        time.sleep(5)
