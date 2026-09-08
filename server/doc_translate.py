import copy
import gc
import os
import time
import re
from pdf2docx import Converter
import trafaret_thread
import subprocess
import comtypes.client
import json
import common
from common import SRC
from deep_translator import GoogleTranslator
import docx
from google.cloud import storage
from google.oauth2 import service_account
import py7zr
import config
import pythoncom

# Сколько страниц PDF конвертируется за один проход.
# Меньше — ниже пиковая память; больше — меньше накладных расходов.
_PDF_PAGES_PER_BATCH = 3


def _pdf_page_count(pdf_path: str) -> int:
    """Возвращает число страниц PDF через PyMuPDF."""
    try:
        import fitz
        with fitz.open(pdf_path) as pdf:
            return pdf.page_count
    except Exception:
        return 0


def _merge_docx_files(input_files: list, output_file: str) -> None:
    """
    Объединяет несколько DOCX-файлов в один.
    Использует первый файл как основу, дописывает XML-элементы body из остальных.
    Держит в памяти не более двух документов одновременно.
    """
    base = docx.Document(input_files[0])
    for path in input_files[1:]:
        src = docx.Document(path)
        for elem in src.element.body:
            base.element.body.append(copy.deepcopy(elem))
        del src
        gc.collect()
    base.save(output_file)
    del base
    gc.collect()


bucket_name = 'liberman-transcriptions'
bucket_name_init = 'llm_knesset_sessions'
credentials = service_account.Credentials.from_service_account_info(json.loads(config.credential))
client = storage.Client(credentials=credentials, project=credentials.project_id)


def get_array_text(text, limit=4000):
    if len(text) < limit:
        return [text]
    result = []
    while len(text) > 0:
        st = text[:limit]
        if len(st) < limit:
            result.append(st)
            text = ''
        else:
            i = len(st) - 1
            while i>0 and st[i] not in ['.', ';']:
                i -=1
            result.append(st[:i+1])
            text = text[i+1:]
    return result


def make_search(word, txt):
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


def check_word(value_words, txt):
    words = value_words.split(';')
    count = 0
    for word in words:
        count += make_search(word, txt)
    return count


def save_file_bucket(file_name, with_zip=True):
    """
    Записать файл в облако
    :param file_name - имя файла
    :param text: - текст файла
    :return:
    """
    # file_name = str(id) + '.txt'
    if with_zip:
        arch_path_file = os.path.splitext(file_name)[0] + '.7z'
        with py7zr.SevenZipFile(arch_path_file, 'w') as arch:
            arch.writeall(file_name)
    else:
        arch_path_file = file_name
    blob_name = os.path.basename(arch_path_file)  # The name of file on GCS once uploaded
    bucket = storage.Bucket(client, bucket_name)  # указать нужный bucket
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(arch_path_file, timeout=3600)  # The content that will be uploaded
    try:
        os.remove(file_name)  # удалить файл с документом
        if with_zip:
            os.remove(arch_path_file)  # удалить и архивный файл
    except:
        pass


class DocTranslate(trafaret_thread.TrafaretThread):
    values_word = ''
    list_blob_name = list()
    time_begin = None
    count_paragraph = 0

    def __init__(self, source, code_function, code_period, description):
        super(DocTranslate, self).__init__(source, code_function, code_period, description)

    def initiation_parameters(self):
        super(DocTranslate, self).initiation_parameters()
        self.par.append({"code": "period", "value": 10})
        self.par.append({"code": "active", "value": 1})

    def load_theme(self):
        self.values_word = ''
        url = 'v2/entity/values?app_code={schema}&object_code=rss_themes&object_id=2'.format(
            schema=config.schema_name)
        ans, is_ok, status = common.send_rest(url)
        if not is_ok:
            common.write_log_db(
                '❌error', SRC, f"Ошибка {ans} для {url}", law_id=self.source)
        else:
            rss_themes = json.loads(ans)
            for data in rss_themes:
                data['value'] = common.translate_from_base(data['value']).strip()
            if len(rss_themes) > 0:
                self.values_word = rss_themes[0]['value']

    def is_new_blob(self, blob_name):
        ans, is_ok, status = common.send_rest(
            "v2/entity/values?app_code=ohi&object_code=transcripts&where=sh_name='{blob_name}'".format(
                blob_name=blob_name))
        if not is_ok:
            common.write_log_db(
                '❌error', SRC, f"Ошибка {ans}", law_id=self.source)
            return False
        else:
            return len(json.loads(ans)) == 0

    def load_init_file_bucket(self, blob_name):
        try:
            bucket = storage.Bucket(client, bucket_name_init)  # указать текущий начальный bucket
            temp_dir = common.current_path
            file_name = temp_dir + '/' + str(blob_name)
            if not os.path.exists(file_name):
                blob = bucket.blob(blob_name)
                os.makedirs(temp_dir, exist_ok=True)
                blob.download_to_filename(file_name)  # это загрузка файла
            return file_name
        except Exception as er:
            file_name = blob_name if blob_name is not None else 'None' + '" в облаке недоступен или отсутствует'
            txt = f'ERROR: {er} ' + file_name
            common.write_log_db(
                '❌error', SRC, f"load_init_file_bucket\nОшибка {txt}", law_id=self.source)

    def prepare_file_document(self, filename, ext='.docx'):
        # преобразование файлов в docx (если нужно)
        filename = filename.replace('/', '\\')
        if ' ' in filename:
            old_filename = filename
            filename = filename.replace(' ', '_')
            os.rename(old_filename, filename)
        if os.path.splitext(filename)[1].upper() != '.DOCX':
            if os.name == 'nt':  # Windows
                if os.path.splitext(filename)[1].upper() in ['.RTF', '.DOC', '.HTML']:
                    word = comtypes.client.CreateObject('Word.Application')
                    doc = word.Documents.Open(filename, ConfirmConversions=False, ReadOnly=True, Encoding='UTF-8')
                    doc.SaveAs(os.path.splitext(filename)[0] + ext, FileFormat=16)
                    doc.Close()
                    word.Quit()
                elif os.path.splitext(filename)[1].upper() == '.PDF':
                    output_docx = os.path.splitext(filename)[0] + ext
                    total_pages = _pdf_page_count(filename)
                    if total_pages <= _PDF_PAGES_PER_BATCH or total_pages == 0:
                        # Короткий документ или не удалось определить страницы — целиком
                        cv = Converter(filename)
                        cv.convert(output_docx, start=0, end=None)
                        cv.close()
                        del cv
                        gc.collect()
                    else:
                        # Длинный документ — конвертируем батчами по _PDF_PAGES_PER_BATCH страниц.
                        # Каждый Converter создаётся и уничтожается отдельно,
                        # чтобы освободить рендер-память после каждого батча.
                        chunk_files = []
                        try:
                            for _start in range(0, total_pages, _PDF_PAGES_PER_BATCH):
                                _end = min(_start + _PDF_PAGES_PER_BATCH, total_pages)
                                chunk_path = (
                                    os.path.splitext(filename)[0]
                                    + f'_chunk_{_start}{ext}'
                                )
                                cv = Converter(filename)
                                cv.convert(chunk_path, start=_start, end=_end)
                                cv.close()
                                del cv
                                gc.collect()
                                chunk_files.append(chunk_path)
                            _merge_docx_files(chunk_files, output_docx)
                        finally:
                            for _f in chunk_files:
                                try:
                                    os.remove(_f)
                                except Exception:
                                    pass
                            gc.collect()
            else:  # Linux
                popen = subprocess.Popen(
                    ['unoconv --doctype=document --format={ext} "{filename}"'.format(ext=ext, filename=filename)],
                    shell=True)
                ans = popen.wait(300)
                if ans != 0:
                    common.write_log_db(
                        '❌error', SRC, 'prepare_file_document\nОшибка конвертации unoconv =' + str(ans), law_id=self.source)
                    return
            # os.remove(filename)  # удаление исходного файла
        filename = os.path.splitext(filename)[0] + ext
        return filename

    def make_translate(self, file_name, data, lang, unit):
        # русский язык
        output_file = '{lang}_'.format(lang=lang) + os.path.splitext(unit)[0] + '.docx'
        date, count = self.translate_word_file(file_name, output_file, lang, self.values_word)
        if count is None:
            common.write_log_db(
                '❌error', SRC, "make_translate\nОшибка {er}".format(er=date), law_id=self.source)
            return False
        data['count'] += count
        if lang == 'ru':
            data['date'] = date
        data['file_size_' + lang] = os.path.getsize(output_file)  # размер текста на указанном языке
        # переименовать файл с учетом языка и даты
        if data['date']:
            new_filename = '{lang}_'.format(lang=lang) + '{date}'.format(date=data['date']) + '.docx'
            os.rename(output_file, new_filename)
        else:
            new_filename = output_file
        save_file_bucket(new_filename)  # записать архивированный файл в облако
        if os.path.exists(output_file):
            os.remove(output_file)  # удалить файл с переведенным документом
        return True

    def delete_files(self, unit):
        filename = common.current_path + '/' + unit
        try:
            if os.path.exists(filename):
                os.remove(filename)  # удалить файл с документом
            elif os.path.exists(filename.replace(' ', '_')):
                os.remove(filename.replace(' ', '_'))  # удалить файл с документом

            filename = common.current_path + os.path.splitext(unit)[0] + '.docx'
            if os.path.exists(filename):
                os.remove(filename)  # удалить файл с документом
            elif os.path.exists(filename.replace(' ', '_')):
                os.remove(filename.replace(' ', '_'))  # удалить файл с документом
        except Exception as er:
            common.write_log_db(
                '❌error', SRC, f"delete_files\nОшибка {er}\n" + filename, law_id=self.source, page=self.count_paragraph)

    def write_db(self, data, unit):
        params = {"schema_name": config.schema_name, "object_code": "transcripts",
                  "values": data}
        ans, is_ok, token, lang = common.login_admin()
        if not is_ok:
            common.write_log_db(
                '❌error', SRC, "write_db\nОшибка {er}".format(er=ans), law_id=self.source)
            return False
        ans, is_ok, status = common.send_rest('v2/entity', 'PUT', params=params, token_user=token)
        if not is_ok:
            common.write_log_db(
                '❌error', SRC, f"write_db\nОшибка {ans}", law_id=self.source, td=time.time() - self.time_begin,
                page=self.count_paragraph)
            return False
        else:
            common.write_log_db(
                '✔️Стенограмма', SRC, str(data), law_id=self.source, td=time.time() - self.time_begin,
                page=self.count_paragraph)
            return True

    def translate_word_file(self, input_file, output_file, lang, value_words):
        """
        Перевод стенограммы заседания Кнессета в формате docx с иврита на указанный язык
        с определением даты заседания в случае русского языка
        :param input_file: - путь документа docx на иврите
        :param output_file: - путь выходного документа docx на указанном языке
        :param lang: - код языка перевода
        :return:
        дата заседания в формате YYYY-MM-DD, если дату удалось определить,
        иначе (или для английского языка) возвращается None
        """
        date_document = None
        count = 0
        try:
            # Open the input Word document
            doc = docx.Document(input_file)
            self.count_paragraph = len(doc.paragraphs)
            print('кол-во параграфов=', self.count_paragraph, 'Перевод на', lang, input_file)
            t0 = time.time()
            n = 0
            for i, data in enumerate(doc.paragraphs):
                if data.text.strip() != '':
                    result = ''
                    texts = get_array_text(data.text)
                    for unit in texts:
                        try:
                            res = GoogleTranslator(target=lang).translate(unit)
                            if res:
                                result += res
                            else:
                                result += unit
                        except Exception as er:
                            common.write_log_db(
                                '❌error', SRC, f"translate_word_file\nОшибка {er}", law_id=self.source,
                                page=i)
                            result += unit
                    init_text = data.text
                    data.text = result

                    count += check_word(value_words, data.text)
                    if lang == 'ru' and date_document is None:
                        result = re.search(
                            r"[(]\d{1,2} (|במרס|בינואר|בפברואר|במרץ|באפריל|במאי|ביוני|ביולי|באוגוסט|בספטמבר|באוקטובר|בנובמבר|בדצמבר) \d{4}",
                            init_text)
                        if result:
                            try:
                                # st = result.string.split('(')[1].split(')')[0].replace('г.', '')
                                st = GoogleTranslator(target='en').translate(
                                    result.string.split('(')[1].split(')')[0].replace('г.', '')).replace(',', '')
                                # print()
                                # print(i + 1, result.string, 'Дата=', st)
                                # print()
                                try:
                                    dt = time.strptime(st, '%d %b %Y')
                                except:
                                    # st = st.replace('בינואר', 'January').replace('февраля', 'February'). \
                                    #     replace('марта', 'March').replace('апреля', 'April').replace('мая', 'May'). \
                                    #     replace('июня', 'June').replace('июля', 'July').replace('августа', 'August'). \
                                    #     replace('сентября', 'September').replace('октября', 'October'). \
                                    #     replace('ноября', 'November').replace('декабря', 'December')
                                    dt = time.strptime(st.strip(), '%B %d %Y')
                                date_document = str(dt.tm_year) + '-' + str(dt.tm_mon).rjust(2, '0') + '-' + \
                                            str(dt.tm_mday).rjust(2, '0')
                            except:
                                date_document = result.string
                            print('date_document', date_document, 'paragraph', i)
                    n = i
                    if n < len(doc.paragraphs) - 1:
                        print('paragraph', i, common.get_duration(time.time() - t0), time.ctime(), end='\r')
                    else:
                        print('paragraph', i, common.get_duration(time.time() - t0), time.ctime())
                # print(data.text)
            print('\n' + time.ctime(), 'end translate count paragraph', n, common.get_duration(time.time() - t0))
            # Save the translated document
            doc.save(output_file)
            # print(f"\nTranslation completed. Translated file saved as: {output_file}")
            return date_document, count
        except Exception as e:
            return f"An error occurred: {e}", None

    def work(self):
        super(DocTranslate, self).work()
        pythoncom.CoInitialize()
        bucket_init = client.get_bucket(bucket_name_init)
        blobs = bucket_init.list_blobs(prefix='')
        blob_file_list = [blob.name for blob in blobs if "." in blob.name]

        if self.make_login():
            self.load_theme()
            for unit in blob_file_list:
                self.time_begin = time.time()
                is_new = self.is_new_blob(unit)
                if not is_new:
                    continue
                file_name = self.load_init_file_bucket(unit)
                if file_name is None:
                    continue
                try:
                    file_name = self.prepare_file_document(file_name)
                except Exception as er:
                    common.write_log_db(
                        '❌error', SRC, f"work\nОшибка {er}\n" + os.path.abspath(file_name),
                        td=time.time() - self.time_begin, law_id=self.source)
                    continue  # пропустить этот документ
                if file_name is None:
                    continue

                data = {}
                data['sh_name'] = unit
                data['theme'] = 2
                data['count'] = 0
                data['file_size_he'] = os.path.getsize(file_name)  # размер текста на иврите
                # русский язык
                if self.make_translate(file_name, data, 'ru', unit):
                # английский язык
                    if self.make_translate(file_name, data, 'en', unit):
                        # удалить созданные или скачанный файл файлы
                        self.delete_files(unit)
                        if os.path.exists(file_name):
                            os.remove(file_name)  # удалить файл с документом
                        # записать в БД факт обработки исходного файла облака
                        if not self.write_db(data, unit):
                            return False  # тайм-аут на одну минуту
            return True
        else:
            return False

# common.current_path = os.path.abspath(os.curdir)
# DocTranslate('DocTranslate', 'DocTranslate', 'period', 'Поток "Перевод стенограмм заседаний Кнессета" загружен').start()
# while True:
#     time.sleep(5)
