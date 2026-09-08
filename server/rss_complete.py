"""
Поток заполнения текстов новостей.

Для новостей, у которых отсутствуют файлы с текстом статей (file IS NULL),
загружает текст по URL, переводит на три языка (ru/en/he) и записывает в облако.
"""
import trafaret_thread
import common
import config
from common import SRC
from translate import _is_challenge_page
from TranslateManager import _is_google_error_page
import json
import asyncio
from deep_translator import GoogleTranslator
from google.cloud import storage
from google.oauth2 import service_account
import py7zr
import time
import os
# newspaper, grab_article, hill_article — тяжёлые зависимости (NLTK, trafilatura, playwright).
# Импортируются лениво внутри load_article(), чтобы не грузить память при старте сервера.

# Зашифрованные учётные данные для Google Cloud Storage
bucket_name = 'llm_news'

# Инициализация клиента Google Cloud Storage
credentials = service_account.Credentials.from_service_account_info(json.loads(config.credential))
client = storage.Client(credentials=credentials, project=credentials.project_id)
bucket = storage.Bucket(client, bucket_name)


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


def save_file_bucket(file_name, text, with_zip=True):
    """
    Записать текст в файл и загрузить в облачный бакет.
    :param file_name: имя файла (без расширения или с любым — будет заменено на .txt)
    :param text: текст файла
    :param with_zip: архивировать файл в .7z перед загрузкой
    """
    # FIX: убран ненужный `global bucket` — модуль только читает переменную, не присваивает
    file_name = os.path.splitext(str(file_name))[0] + '.txt'
    # FIX: было `f = open(...); with f:` — антипаттерн (файл открыт до with)
    with open(file_name, 'w', encoding='utf-8') as f:
        f.write(text)
    if with_zip:
        arch_path_file = os.path.splitext(file_name)[0] + '.7z'
        with py7zr.SevenZipFile(arch_path_file, 'w') as arch:
            arch.writeall(file_name)
    else:
        arch_path_file = file_name
    blob_name = os.path.basename(arch_path_file)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(arch_path_file, timeout=3600)
    # FIX: было голое `except:` — ловило SystemExit/KeyboardInterrupt
    try:
        os.remove(file_name)
        if with_zip:
            os.remove(arch_path_file)
    except Exception:
        pass


class CompleteRSS(trafaret_thread.TrafaretThread):
    """
    Поток заполнения текстов новостных статей.

    Для каждой статьи без текста (file IS NULL):
    1. Загружает HTML статьи по URL (newspaper → hill_article → grab_article)
    2. Переводит текст на ru/en/he
    3. Сохраняет переводы в облако (GCS) и обновляет запись в БД
    """
    def __init__(self, source, code_function, code_period, description):
        super(CompleteRSS, self).__init__(source, code_function, code_period, description)
        self.list_complete = []   # список статей без текста
        self.global_count = 0    # общее кол-во статей в очереди
        self.global_new = 0      # кол-во успешно обработанных
        self.global_error = 0    # кол-во ошибок
        self.last_length = 0     # длина последнего обработанного текста

    def initiation_parameters(self):
        super(CompleteRSS, self).initiation_parameters()
        self.par.append({"code": "period", "value": 10})
        self.par.append({"code": "active", "value": 1})

    def load_list_complete(self):
        """Загружает из БД список статей, у которых отсутствует текст (file IS NULL)."""
        self.list_complete = []  # освобождаем старые данные перед загрузкой
        where = 'file is null'
        ans, is_ok, status = common.send_rest(
            'v2/entity/values?app_code={app_code}&object_code=rss_history&where={where}&column_order=id'.format(
                app_code=config.schema_name, where=where), params={"columns": "id, url"})
        if not is_ok:
            common.write_log_db(
                '❌error', SRC, f"load_list_complete\nОшибка {ans}", law_id=self.source)
            return False
        self.list_complete = json.loads(ans)
        # FIX: было len(ans) — длина сырой JSON-строки (для "[]" это 2 > 0 = True)
        return len(self.list_complete) > 0

    def load_article(self, ind, values):
        """
        Загружает и переводит одну статью.
        Цепочка: newspaper3k → hill_article (httpx/curl_cffi) → grab_article (Playwright).
        Возвращает True при успехе, False при неудаче.
        """
        t = time.time()
        if 'url' in values and values['url']:
            values['error_translator'] = False
            ident = values['id']
            url = values['url']
            meta_img = None
            txt = None

            # Попытка 1: newspaper3k
            from newspaper import Article  # ленивый импорт: NLTK загружается только здесь
            article = Article(
                url,
                request_headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                                  'Chrome/124.0.0.0 Safari/537.36'},
                request_timeout=15
            )
            article.download()
            _download_exc = article.download_exception_msg
            if _download_exc:
                if '410 Client Error' in _download_exc:
                    # Ресурс удалён намеренно и навсегда — fallback бесполезен
                    del article
                    params = {"schema_name": config.schema_name, "object_code": "rss_history",
                              "values": {'id': values['id'], 'file': -1,
                                         'error_translator': False}}
                    ans, is_ok, status = common.send_rest('v2/entity', 'PUT', params=params, token_user=self.token)
                    if not is_ok:
                        common.write_log_db(
                            '❌error', SRC, f"load_article\nОшибка {ans}\n" + json.dumps(params, indent=4, ensure_ascii=False),
                            page=ind + 1, td=time.time() - t, law_id=self.source)
                        self.global_error += 1
                    return False
                # 403 и прочие ошибки — переходим к fallback'ам ниже
            else:
                article.parse()
                if article.text and len(article.text) > 100 and not _is_challenge_page(article.text):
                    meta_img = article.meta_img
                    txt = article.text
            del article  # освобождаем HTML + NLP-структуры newspaper3k (~десятки МБ на статью)

            # Попытка 2: hill_article (httpx HTTP/2, AMP-варианты, curl_cffi — обход 403)
            if not txt:
                try:
                    import hill_article  # ленивый импорт: trafilatura + readability загружаются только здесь
                    meta_img, txt = hill_article.main(url)
                    if txt and _is_challenge_page(txt):
                        meta_img, txt = None, None
                except Exception:
                    pass

            # Попытка 3: grab_article (Playwright — рендерит JS)
            if not txt:
                try:
                    import grab_article  # ленивый импорт: playwright загружается только здесь
                    meta_img, txt = self._async_loop.run_until_complete(grab_article.main(url))
                    if txt and _is_challenge_page(txt):
                        meta_img, txt = None, None
                except Exception:
                    pass

            if not txt:
                msg = _download_exc or 'Пустой текст статьи после всех попыток'
                # common.write_log_db(
                #     '⚠️warning', self.source, msg,
                #     page=ind + 1, td=time.time() - t,
                #     law_id=f'{self.global_count}\n id={ident}',
                #     file_name=common.get_computer_name())
                self.global_error += 1
                return False

            common.write_log_db(
                '✔️done', SRC, f'Прочитана статья {self.global_count}\n id={ident}',
                page=ind + 1, td=time.time() - t, law_id=self.source)

            values['meta_img'] = meta_img or ''
            self.last_length = len(txt)
            text = get_array_text(txt)
            text_ru = ''
            text_en = ''
            text_he = ''
            # Создаём три транслятора один раз перед циклом — каждый хранит HTTP-сессию внутри.
            # Ранее GoogleTranslator(...) создавался на каждую итерацию (десятки объектов на статью).
            translator_ru = GoogleTranslator(target='ru')
            translator_en = GoogleTranslator(target='en')
            translator_iw = GoogleTranslator(target='iw')
            for unit in text:
                try:
                    res = translator_ru.translate(unit)
                    if res and not _is_google_error_page(res):
                        text_ru += res
                    else:
                        text_ru += unit
                        values['error_translator'] = True
                except Exception as er:
                    text_ru += unit
                    values['error_translator'] = True
                    print('--> ru', f'{er}')
                try:
                    res = translator_en.translate(unit)
                    if res and not _is_google_error_page(res):
                        text_en += res
                    else:
                        text_en += unit
                        values['error_translator'] = True
                except Exception as er:
                    text_en += unit
                    values['error_translator'] = True
                    print('--> en', f'{er}')
                try:
                    res = translator_iw.translate(unit)
                    if res and not _is_google_error_page(res):
                        text_he += res
                    else:
                        text_he += unit
                        values['error_translator'] = True
                except Exception as er:
                    text_he += unit
                    values['error_translator'] = True
                    print('--> he', f'{er}')
            del translator_ru, translator_en, translator_iw  # освобождаем HTTP-сессии после перевода
            save_file_bucket('en_' + str(values['id']), text_en)
            save_file_bucket('ru_' + str(values['id']), text_ru)
            save_file_bucket('he_' + str(values['id']), text_he)
            values['file'] = len(txt)
            del txt, text_ru, text_en, text_he  # освобождаем переведённые тексты

            # Обновление записи в БД: размер файла, картинка, статус перевода
            params = {"schema_name": config.schema_name, "object_code": "rss_history",
                      "values": {'id': values['id'], 'file': values['file'],
                                 'meta_img': values.get('meta_img', ''),
                                 'error_translator': values['error_translator']}}
            ans, is_ok, status = common.send_rest('v2/entity', 'PUT', params=params, token_user=self.token)
            if not is_ok:
                common.write_log_db(
                    '❌error', SRC, f"Ошибка {ans}\n" + json.dumps(params, indent=4, ensure_ascii=False) +
                                           f'\n{self.global_count}\n id={ident}',
                    page=ind+1, td=time.time() - t,
                    law_id=self.source)
                self.global_error += 1
                return False
            else:
                self.global_new += 1
                st = f"id={values['id']} file_size={values['file']}"
                common.write_log_db(
                    '➕info', SRC, 'Добавлены в облако тексты статей для ' + st + '\n' +
                                  values['url'] + f'{self.global_count}\n id={ident}',
                    page=ind+1, td=time.time() - t, law_id=self.source)
                return True
        else:
            return False

    def work(self):
        super(CompleteRSS, self).work()
        if common.get_value_config_param('active', self.par) != 1:
            return False
        if self.load_list_complete() and self.make_login():
            self.global_count = len(self.list_complete)
            common.write_log_db('✈️Start', SRC,
                                f"Начало работы по заполнению отсутствующих текстов новостей\n"
                                f"отсутствующих текстов={self.global_count}",
                                law_id=self.source, page=self.global_count)
            self.global_error = 0
            self.global_new = 0
            t0 = time.time()
            for j, data in enumerate(self.list_complete):
                try:
                    self.load_article(j, data)
                    print(self.source, 'id=', data['id'], 'count=', self.global_count, 'new=', self.global_new,
                          'error=', self.global_error, 'length', self.last_length, 'td=', time.time()-t0)
                except Exception as er:
                    self.global_error += 1
                    ident = data['id']
                    common.write_log_db(
                        '❌warning', SRC, f"Ошибка {er}; {data.get('url', '')} {self.global_count}\n id={ident}",
                        law_id=self.source, page=j)
            self.list_complete = []  # освобождаем список после обработки
            # FIX: finish_text и return True перенесены внутрь if-блока.
            # Раньше были снаружи — при ошибке загрузки/логина метод
            # показывал стейл-данные предыдущего цикла и возвращал True (ложный успех).
            st = '➕ ' if self.global_new else ''
            self.finish_text += (f'Добавление файлов для новостей:\nВсего пропусков={self.global_count}'
                                 f'\n{st}Добавлено={self.global_new}\nОшибок={self.global_error}')
            return True


if __name__ == "__main__":
    CompleteRSS('CompleteRSS', 'CompleteRSS', 'period', 'Поток "Добавление полных текстов новостей" загружен').start()
    while True:
        time.sleep(5)
