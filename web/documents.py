"""Документы: загрузка файла в бакет Google Cloud Storage и запись метаданных документа в БД (таблица nsi_documents).

Загрузка — только администратор. Файл кладётся в отдельный бакет DOCS_BUCKET (env, по умолчанию ohi-docs), а не в бакет
текстов новостей (llm_news). Метаданные пишутся через v2/execute (SQL с токеном superadmin — значения только через
escape_sql_literal / int). Таблицу создаёт scripts/create_nsi_documents.sql (в базе она не создаётся автоматически).

Порядок загрузки: проверка файла → sha256 → такой документ уже есть? (возвращается существующий, дубль не создаётся) →
файл в бакет → метаданные в БД; если запись в БД не удалась — файл из бакета удаляется (не остаётся «сирот»).
"""
import datetime
import hashlib
import json
import mimetypes
import os
import re
import uuid

import common
import config
from common import get

DOCS_BUCKET = os.environ.get('DOCS_BUCKET', 'ohi-docs')
MAX_SIZE = 30 * 1024 * 1024  # Cloud Run принимает запрос не больше 32 МБ
ALLOWED_EXT = ('pdf', 'doc', 'docx', 'odt', 'rtf', 'txt', 'md', 'xls', 'xlsx', 'ods', 'csv', 'ppt', 'pptx', 'zip', '7z',
               'jpg', 'jpeg', 'png')
LIST_LIMIT = 500
COLUMNS = 'id, sh_name, blob_name, bucket, content_type, size, sha256, description, uploaded_by, inserted_date'


def table():
    return '{schema}.nsi_documents'.format(schema=config.SCHEMA)


def _execute(script):
    """SQL через REST (v2/execute). Возвращает (строки, текст_ошибки); ошибка — пустая строка при успехе."""
    ans, is_ok, status = common.send_rest('v2/execute', 'PUT', params={"script": script}, token_user=get('token'))
    if not is_ok:
        return [], str(ans)
    try:
        return json.loads(ans), ''
    except (TypeError, ValueError):
        return [], ''


def table_missing(error):
    return 'does not exist' in error or 'не существует' in error


def safe_name(name):
    """Имя файла без пути и опасных символов (для имени объекта в бакете и для показа)."""
    name = os.path.basename(str(name or '').replace('\\', '/')).strip()
    name = re.sub(r'[^\w.\- ()]+', '_', name, flags=re.UNICODE).strip(' .')
    return name[:120] or 'document'


def extension(name):
    return os.path.splitext(name)[1].lower().lstrip('.')


def make_blob_name(name, now=None):
    """documents/ГГГГ/ММ/<12 hex>_<имя>: уникальное имя объекта в бакете."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return 'documents/{:%Y/%m}/{}_{}'.format(now, uuid.uuid4().hex[:12], safe_name(name))


def get_docs_bucket():
    import cloud
    return cloud.get_bucket(DOCS_BUCKET)


def list_documents():
    """Документы (новые сверху). Возвращает (строки, ошибка); ошибка 'table_missing' — таблицы ещё нет."""
    rows, error = _execute('select {cols} from {table} order by id desc limit {limit}'.format(
        cols=COLUMNS, table=table(), limit=LIST_LIMIT))
    if error:
        return [], 'table_missing' if table_missing(error) else error
    return rows, ''


def find_by_hash(sha):
    rows, error = _execute("select {cols} from {table} where sha256='{sha}' limit 1".format(
        cols=COLUMNS, table=table(), sha=common.escape_sql_literal(sha)))
    return (rows[0] if rows else None), error


def get_document(doc_id):
    rows, error = _execute('select {cols} from {table} where id={id}'.format(
        cols=COLUMNS, table=table(), id=int(doc_id)))
    return (rows[0] if rows else None), error


def upload(filename, data, description='', user=''):
    """Загружает документ. data — байты файла. Возвращает {'ok', 'message', 'doc', 'duplicate'}."""
    name = safe_name(filename)
    ext = extension(name)
    if ext not in ALLOWED_EXT:
        return {'ok': False, 'message': 'Тип файла не поддерживается: .{}. Разрешены: {}'.format(ext, ', '.join(ALLOWED_EXT))}
    if not data:
        return {'ok': False, 'message': 'Файл пуст'}
    if len(data) > MAX_SIZE:
        return {'ok': False, 'message': 'Файл больше {} МБ'.format(MAX_SIZE // (1024 * 1024))}

    sha = hashlib.sha256(data).hexdigest()
    existing, error = find_by_hash(sha)
    if error:
        return {'ok': False, 'message': 'Ошибка проверки дубликата: ' + ('таблица nsi_documents не создана' if table_missing(error) else error)}
    if existing:
        return {'ok': True, 'duplicate': True, 'doc': existing,
                'message': 'Такой документ уже загружен (id={}, «{}»)'.format(existing['id'], existing['sh_name'])}

    content_type = mimetypes.guess_type(name)[0] or 'application/octet-stream'
    blob_name = make_blob_name(name)
    try:
        bucket = get_docs_bucket()
        blob = bucket.blob(blob_name)
        blob.upload_from_string(data, content_type=content_type)
    except Exception as er:
        text = '{}: {}'.format(type(er).__name__, er)
        if 'NotFound' in type(er).__name__ or '404' in text:
            text = 'бакет «{}» не найден — создайте его в GCP или задайте DOCS_BUCKET'.format(DOCS_BUCKET)
        return {'ok': False, 'message': 'Ошибка загрузки в бакет: ' + text}

    description = (description or '').strip()[:2000]
    insert = ("insert into {table} (sh_name, blob_name, bucket, content_type, size, sha256, description, uploaded_by) "
              "values ('{name}', '{blob}', '{bucket}', '{ctype}', {size}, '{sha}', {desc}, '{user}') returning {cols}").format(
        table=table(), name=common.escape_sql_literal(name), blob=common.escape_sql_literal(blob_name),
        bucket=common.escape_sql_literal(DOCS_BUCKET), ctype=common.escape_sql_literal(content_type), size=len(data),
        sha=sha, desc=("'" + common.escape_sql_literal(description) + "'") if description else 'null',
        user=common.escape_sql_literal(user or ''), cols=COLUMNS)
    rows, error = _execute(insert)
    if error or not rows:
        try:  # метаданные не записались — файл из бакета убираем, чтобы не осталось «сироты»
            blob.delete()
        except Exception:
            pass
        reason = 'таблица nsi_documents не создана (scripts/create_nsi_documents.sql)' if table_missing(error) else (error or 'нет ответа')
        return {'ok': False, 'message': 'Ошибка записи метаданных в БД: ' + reason}
    return {'ok': True, 'duplicate': False, 'doc': rows[0], 'message': 'Документ загружен (id={})'.format(rows[0]['id'])}


def download(doc_id):
    """Содержимое документа: (байты, имя, content_type) или (None, сообщение_об_ошибке, None)."""
    doc, error = get_document(doc_id)
    if error or not doc:
        return None, error or 'Документ не найден', None
    try:
        import cloud
        blob = cloud.get_bucket(doc.get('bucket') or DOCS_BUCKET).blob(doc['blob_name'])
        return blob.download_as_bytes(), doc['sh_name'], doc.get('content_type') or 'application/octet-stream'
    except Exception as er:
        return None, 'Файл недоступен в бакете: {}'.format(er), None


def delete(doc_id):
    """Удаляет документ: сначала запись в БД, затем файл. Возвращает (успех, сообщение)."""
    doc, error = get_document(doc_id)
    if error or not doc:
        return False, error or 'Документ не найден'
    _, error = _execute('delete from {table} where id={id}'.format(table=table(), id=int(doc_id)))
    if error:
        return False, 'Ошибка удаления записи: ' + error
    try:
        import cloud
        cloud.get_bucket(doc.get('bucket') or DOCS_BUCKET).blob(doc['blob_name']).delete()
    except Exception as er:
        return True, 'Запись удалена, файл в бакете удалить не удалось: {}'.format(er)
    return True, 'Документ удалён'


def prepare_form(request):
    """Форма «Документы» (только администратор): список документов и параметры загрузки."""
    answer = dict()
    st = common.init_form(request, '/documents/')
    if st:
        answer['redirect'] = st
        return answer
    rows, error = list_documents()
    answer['data'] = rows
    answer['table_missing'] = error == 'table_missing'
    if error and error != 'table_missing':
        from flask import flash
        flash('Ошибка получения документов: ' + error, 'warning')
    answer['bucket'] = DOCS_BUCKET
    answer['max_size'] = MAX_SIZE
    answer['allowed'] = list(ALLOWED_EXT)
    return answer
