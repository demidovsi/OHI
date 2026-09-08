"""
Считывание топ-новостей из WorldNews API.

Запрашивает ленту по REST API, ищет поисковые образы в каждой новости,
переводит на три языка и записывает в БД и облако.

Текст статьи загружается по URL (newspaper3k → hill_article → grab_article),
переводится на три языка и записывается в файлы бакета.

Конфигурация в БД (code_function='WorldNews'):
  api_key  — ключ API (is_number=False), например 57cd04c607fb4839904f81cff3347bb3
  period   — период опроса в минутах (по умолчанию 10)
  active   — 1=активен, 0=остановлен

В поле rss_list.url хранится полный URL запроса с параметрами, например:
  https://api.worldnewsapi.com/top-news?source-country=ru&language=ru
"""
import datetime
import html as html_module
import time

import requests

import cloud
import common
from common import SRC
import trafaret_thread
import translate

_API_BASE = 'https://api.worldnewsapi.com/top-news'


class WordNewsRSS(trafaret_thread.TrafaretThread):
    """
    Поток загрузки топ-новостей из WorldNews API.

    Структура ответа API:
      {"top_news": [{"news": [{id, title, summary, url, image,
                               publish_date, author, authors, language,
                               category, source_country}, ...]}]}
    Текст статьи загружается по полю url (не из поля text API).
    """

    def __init__(self, source, code_function, code_period, description, rss_id):
        self.print_load = False
        self.rss_id = rss_id
        self.rss_themes = []
        super().__init__(source, code_function, code_period, description)

    def initiation_parameters(self):
        super().initiation_parameters()
        self.par.append({'code': 'period', 'value': 10})
        self.par.append({'code': 'active', 'value': 1})

    def _get_api_key(self):
        """Загружает API-ключ из конфигурации БД (WorldNews / api_key, is_number=False)."""
        par = common.load_config_params('WorldNews')
        key = common.get_value_config_param('api_key', par, default=None)
        return str(key) if key is not None else ''

    def fetch_news(self, rss):
        """
        Запрашивает топ-новости из WorldNews API.
        URL (с параметрами source-country, language и т.п.) берётся из rss['url'].
        Возвращает плоский список news-объектов, пустой список при 429 или None при ошибке.

        При 429 Too Many Requests делает до 2 повторных попыток с паузой согласно
        заголовку Retry-After (или 60 сек по умолчанию, но не более 120 сек).
        Если лимит исчерпан окончательно — логирует как ⚠️warning и возвращает [],
        чтобы поток не помечался как ошибочный (❌).

        При таймауте/сетевой ошибке (эндпоинт top-news иногда долго собирает
        новости на стороне API) делает до 2 повторных попыток с паузой
        _RETRY_PAUSE сек. Если ошибка сохраняется — логирует как ⚠️warning
        (временная проблема стороннего API, не наша ошибка) и возвращает None.
        """
        api_key = self._get_api_key()
        if not api_key:
            common.write_log_db(
                '❌error', SRC,
                'fetch_news\nНе задан API-ключ WorldNews (code_function=WorldNews, code=api_key, is_number=False)',
                page=rss['id'], law_id=self.source)
            return None

        url = rss.get('url') or _API_BASE
        _MAX_RETRIES = 2
        _REQUEST_TIMEOUT = 45
        _RETRY_PAUSE = 5
        data = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = requests.get(url, headers={'x-api-key': api_key}, timeout=_REQUEST_TIMEOUT)
            except requests.exceptions.RequestException as err:
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_PAUSE)
                    continue
                common.write_log_db(
                    '⚠️warning', SRC, f'fetch_news\nОшибка запроса WorldNews API: {err}\n{url}',
                    page=rss['id'], law_id=self.source)
                return None

            if response.ok:
                data = response.json()
                break

            self.status_code = response.status_code

            if response.status_code == 429:
                # Лимит запросов API — ждём и повторяем
                retry_after = response.headers.get('Retry-After')
                wait = int(retry_after) if retry_after and retry_after.isdigit() else 60
                wait = min(wait, 120)  # не блокируем поток дольше 2 минут
                if attempt < _MAX_RETRIES:
                    time.sleep(wait)
                    continue
                # Все попытки исчерпаны — это ожидаемое ограничение API, не ошибка
                common.write_log_db(
                    '⚠️warning', SRC,
                    f'fetch_news\nWorldNews API: {response.status_code} {response.reason}\n{url}',
                    page=rss['id'], law_id=self.source)
                return []  # пустой список — поток не будет помечен как ❌

            # Другие HTTP-ошибки
            level = '⚠️warning' if response.status_code == 402 else '❌error'
            common.write_log_db(
                level, SRC,
                f'fetch_news\nWorldNews API: {response.status_code} {response.reason}\n{url}',
                page=rss['id'], law_id=self.source)
            return None

        if data is None:
            return None
        items = []
        for group in data.get('top_news', []):
            items.extend(group.get('news', []))
        return items

    def make_values(self, rss, item):
        """
        Маппинг полей ответа WorldNews API → словарь values для хранения в БД.

        Поля API → values:
          title        → title_ru/en/he   (перевод)
          summary      → description_ru/en/he (перевод, очистка HTML)
          url          → url
          image        → meta_img
          publish_date → public_date      (уже в формате "YYYY-MM-DD HH:MM:SS" UTC)
          author       → author
          language     → lang
        """
        lang = item.get('language') or rss.get('lang', 'ru')
        values = {
            'rss': rss['id'],
            'lang': lang,
            'error_translator': False,
        }

        # Заголовок
        title = html_module.unescape(item.get('title') or '')
        if title:
            err, values['title_ru'], values['title_en'], values['title_he'] = (
                translate.make_translate(title, lang))
            values['error_translator'] = values['error_translator'] or err

        # Ссылка
        values['url'] = item.get('url') or ''

        # Краткое описание (summary)
        summary = html_module.unescape(item.get('summary') or '')
        if summary:
            desc = cloud.make_description(summary)
            err, values['description_ru'], values['description_en'], values['description_he'] = (
                translate.make_translate(desc, lang))
            values['error_translator'] = values['error_translator'] or err

        # Автор: предпочитаем массив authors (может содержать несколько),
        # иначе берём строку author
        authors_list = [a for a in (item.get('authors') or []) if a]
        if authors_list:
            author = ', '.join(authors_list)
        else:
            author = item.get('author') or ''
        if author:
            values['author'] = author

        # Изображение
        values['meta_img'] = item.get('image') or ''

        # Дата публикации (API возвращает "2026-03-04 02:26:02" — уже UTC)
        values['public_date'] = item.get('publish_date') or ''

        # Время записи
        values['at_date_time'] = datetime.datetime.now(datetime.timezone.utc).isoformat()

        return values

    def analyses_news(self, rss, items):
        """
        Обработка списка новостей:
        1. Проверка дубликата по URL
        2. Перевод заголовка и описания
        3. Поиск поисковых образов (сначала в заголовке/описании, затем в тексте)
        4. Запись в БД, уведомление в TG, сохранение текстов в облако
        """
        t0 = time.time()
        rss['count'] = 0
        rss['count_new'] = 0
        self.global_count = len(items)

        for j, item in enumerate(items):
            try:
                self.number = j + 1
                rss['count'] += 1

                url = item.get('url') or ''
                if not url:
                    continue

                # Быстрая проверка дубликата по URL
                values = {'url': url, 'rss': rss['id']}
                exist = common.is_exist_object(values, self.token)
                if exist is not None and not exist:
                    values = self.make_values(rss, item)
                    common.seek(self.rss_themes, values)

                    # Загружаем текст статьи по URL, переводим и сохраняем в бакет
                    is_article = translate.load_article(values, init_lang=values['lang'])

                    # Если темы не найдены в заголовке/описании — ищем в тексте статьи
                    if len(values['themes']) == 0 and is_article:
                        common.seek_article(self.rss_themes, values)

                    if values['themes']:
                        ok_write = common.write_history(values, self.token, rss, self.source)
                        if ok_write:
                            themes = ''
                            for theme in values['themes']:
                                themes = themes + ', ' if themes else themes
                                themes += common.get_name_theme(self.rss_themes, theme)
                            common.make_tg(self.source, themes, values, rss, j, self.global_count)
                            for theme in values['themes']:
                                common.make_theme(theme, values, self.source, self.token)
                            if is_article:
                                cloud.save_file_bucket('en_' + str(values['id']), values['text_en'])
                                cloud.save_file_bucket('ru_' + str(values['id']), values['text_ru'])
                                cloud.save_file_bucket('he_' + str(values['id']), values['text_he'])

                # Фиксируем новость как просмотренную в log_rss_history
                exists = common.is_exist_object(values, self.token)
                if exists is not None and not exists:
                    common.fix_new(values, self.token)

            except Exception as er:
                common.write_log_db(
                    '❌error', SRC,
                    f'analyses_news\nj={j + 1} из {self.global_count}\nОшибка {er}\nanalyses_news',
                    law_id=self.source, td=time.time() - t0)
            time.sleep(0.5)

        st_new = '➕ ' if rss['count_new'] else ''
        self.finish_text += (
            f'Закончена обработка WorldNews для "{rss["sh_name"]}" (ID={rss["id"]}); '
            f'новостей={self.global_count};\n{st_new}записано={rss["count_new"]}; обработано={rss["count"]}'
        )

    def work(self):
        super().work()
        if common.get_value_config_param('active', self.par) != 1:
            return False

        result, self.rss = common.load_rss(self.rss_id, self.source)
        if result:
            result, self.rss_themes = common.load_list_themes(self.source)
            if result:
                result = self.make_login()
                if result and self.rss.get('stop') != True:
                    common.write_log_db(
                        '✈️Start', self.source,
                        f"Начало работы по опросу WorldNews API для [{self.rss['sh_name']}] ID={self.rss['id']}",
                        page=self.rss['id'], law_id=self.rss['sh_name'] + '\n' + self.source)
                    if not self.rss_themes:
                        self.finish_text = 'Отсутствуют поисковые образы для WorldNews'
                    else:
                        items = self.fetch_news(self.rss)
                        if items is not None:
                            self.is_error = False
                            self.analyses_news(self.rss, items)
                            del items  # список новостей больше не нужен — освобождаем память
                        else:
                            self.is_error = True
                            return False
                    return True
                else:
                    return False
        return result


if __name__ == '__main__':
    WordNewsRSS('WorldNews', 'WorldNews', 'period',
                'Поток "Поиск тем в топ-новостях WorldNews API"', 40).start()
    while True:
        time.sleep(5)
