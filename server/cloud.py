import html as html_module
import json
import os
import re

from google.cloud import storage
from google.oauth2 import service_account
import py7zr

import common
import config

bucket_name = 'llm_news'

# --- Фильтрация мусорных строк из текста статей ---

# Интерфейсные фразы, которые парсеры (trafilatura, readability) иногда
# захватывают как "текст": виджеты ошибок, подписки, соцсети и т.п.
_JUNK_LINE_RE = re.compile(
    r'нашли\s+ошибку'               # "Нашли ошибку?"
    r'|сообщить\s+об\s+ошибке'      # "Сообщить об ошибке"
    r'|связаться\s+с\s+нами'        # "Связаться с нами"
    r'|подпишитесь\s+на'            # "Подпишитесь на рассылку / канал"
    r'|подписаться\s+на\s+рассылку',
    re.IGNORECASE,
)

# Строки, целиком состоящие из даты/времени публикации:
# "15 января 2025 г., 17:54 (GMT+2)" / "12 марта 2026 г."
_DATE_ONLY_LINE_RE = re.compile(
    r'^\s*\d{1,2}\s+\w+\s+\d{4}\s*г?\.?\s*,?\s*(\d{1,2}:\d{2})?\s*(\(.*?\))?\s*$',
)

_bucket = None  # инициализируется при первом обращении


def get_bucket():
    """Ленивая инициализация GCS-клиента — не падает при импорте если CREDENTIAL не задан."""
    global _bucket
    if _bucket is None:
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(config.credential))
        client = storage.Client(credentials=credentials, project=credentials.project_id)
        _bucket = storage.Bucket(client, bucket_name)
    return _bucket


def save_file_bucket(file_name, text, with_zip=False):
    """
    Записать файл в облако.
    :param file_name - имя файла
    :param text: - текст файла
    :param with_zip: - признак архивирования
    :return:
    """
    bucket = get_bucket()
    file_name = os.path.splitext(str(file_name))[0] + '.txt'
    f = open(file_name, 'w', encoding='utf-8')
    with f:
        f.write(text)
    if with_zip:
        arch_path_file = os.path.splitext(file_name)[0] + '.7z'
        with py7zr.SevenZipFile(arch_path_file, 'w') as arch:
            arch.writeall(file_name)
    else:
        arch_path_file = file_name
    blob_name = os.path.basename(arch_path_file)  # The name of file on GCS once uploaded
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(arch_path_file, timeout=3600)  # The content that will be uploaded
    try:
        os.remove(file_name)  # удалить файл с документом
        if with_zip:
            os.remove(arch_path_file)  # удалить и архивный файл
    except:
        pass


def make_description(init_description):
    array = [
        '<![CDATA[', ']]>', '<p>', '</p>', '<!-- wp:paragraph -->', '<!-- /wp:paragraph -->', '<!-- wp:image -->',
        '<!-- wp:heading -->', '<blockquote class="wp-block-quote">', '</blockquote>', '<ol>', '</ol>',
        '<li>', '</li', '<ul>', '</ul>', '<em>', '</em>', '<u>', '</u>', '<b>', '</b>'
    ]
    array_begin = [
        '<!-- wp:html -->', '<!-- wp:image -->',
    ]
    array_end = [
        '<!-- /wp:html -->', '<!-- /wp:image -->'
    ]

    def delete_tag(tag, txt):
        while '<' + tag in txt:
            ind_b = txt.index('<' + tag)
            ind_e = ind_b
            while ind_e < len(txt) - 1:
                ind_e += 1
                if txt[ind_e] in ['<', '>']:
                    break
            ind_e += 1
            if ind_e > ind_b:
                txt = txt[:ind_b] + txt[ind_e:]
            else:
                txt = txt[:ind_e]
        txt = txt.replace('</' + tag + '>', '')
        return txt

    if init_description:
        for data in array:
            init_description = init_description.replace(data, '')
        description = ''
        init_description = init_description.split('\n')
        skip = False
        i = 0
        while i < len(init_description):
            row = init_description[i].strip()
            if row in array_begin:
                skip = True
            if not skip:
                description += row + '\n'
            i += 1
            if row in array_end:
                skip = False

        description = delete_tag('span', description)
        description = delete_tag('div', description)
        description = delete_tag('a', description)
        description = delete_tag('time', description)
        description = delete_tag('source', description)
        description = delete_tag('picture', description)
        description = delete_tag('script', description)
        description = delete_tag('h1', description)
        description = delete_tag('h2', description)
        description = delete_tag('h3', description)
        description = delete_tag('figure', description)
        description = delete_tag('strong', description)
        description = delete_tag('ins', description)
        description = delete_tag('', description)

        while '<!--' in description:
            ind_begin = description.index('<!--')
            ind_end = description.index('-->')
            if ind_end > ind_begin:
                description = description[:ind_begin] + description[ind_end + 3:]
            else:
                description = description[:ind_end] + description[ind_end + 3:]

        if description[0:4] == '<img':
            i = description.index('/>')
            description = description[i + 2:]

        description = description.split('<br/>')
        description = description[1] if len(description) > 1 else description[0]

        description = description.split('<br />')
        description = description[1] if len(description) > 1 else description[0]

        description = description.replace('&nbsp;', ' ').replace('&nbsp', ' ')
        description = html_module.unescape(description)
        description = description.replace('">', ' ')
        description = description.replace('>', ' ')
        # После replace('>', ' ') все '>' исчезли, но незакрытые теги типа
        # '<p class="x"' превращаются в '<p class="x" ' — убираем остатки.
        description = re.sub(r'</?[a-zA-Z][a-zA-Z0-9]*', '', description)
        while '\n\n\n' in description:
            description = description.replace('\n\n\n', '\n\n')

        # Фильтрация строк-мусора: виджеты обратной связи, метки даты/времени и т.п.
        lines = description.split('\n')
        lines = [
            ln for ln in lines
            if not _JUNK_LINE_RE.search(ln) and not _DATE_ONLY_LINE_RE.match(ln)
        ]
        description = '\n'.join(lines)
    else:
        return ''
    return description.strip()


def check_exist_blob(filename):
    """
    Проверяет, существует ли файл в указанном bucket на Google Cloud Storage.

    Аргументы:
    bucket -- объект bucket для поиска файл
    filename -- имя файла, который нужно найти

    Возвращает:
    True, если файл существует в bucket, иначе False
    """
    return any(blob.name == filename for blob in get_bucket().list_blobs(prefix=filename))
