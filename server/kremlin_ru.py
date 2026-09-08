"""
Парсер новостей с сайта kremlin.ru (Президент России).

Скрейпит страницы новостей, проверяет на наличие поисковых образов,
переводит найденные совпадения на три языка и записывает в БД и облако.

Структура страницы:
  https://kremlin.ru/events/president/news       — первая страница
  https://kremlin.ru/events/president/news/page/N — страница N

Каждая новость — div.hentry с атрибутом data-url и <time itemprop="datePublished">.
"""
import re
import datetime
import time
import traceback

import requests
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup

import cloud
import common
from common import SRC
import trafaret_thread
import translate

BASE_URL = 'https://kremlin.ru'
NEWS_URL = BASE_URL + '/events/president/news'

http_adapter = HTTPAdapter(max_retries=5)


class KremlinRu(trafaret_thread.TrafaretThread):
    """
    Поток парсинга новостей с сайта kremlin.ru.

    Перебирает страницы новостей (начиная с number_page и до 1),
    для каждой новости проверяет наличие в БД, ищет поисковые образы,
    переводит и записывает.
    """
    global_new = 0        # кол-во новых записанных новостей за цикл
    global_error = 0      # кол-во ошибок за цикл
    number_page = None    # номер текущей страницы новостей

    url = BASE_URL
    url_news = NEWS_URL

    def __init__(self, source, code_function, code_period, description, rss_id):
        self.rss_id = rss_id
        # Изменяемый атрибут — на уровне экземпляра, не класса
        self.rss_themes = []
        super(KremlinRu, self).__init__(source, code_function, code_period, description)

    def initiation_parameters(self):
        """Задаёт параметры по умолчанию: период опроса (10 мин) и активность."""
        super(KremlinRu, self).initiation_parameters()
        self.par.append({"code": "period",      "value": 10})
        self.par.append({"code": "active",      "value": 1})
        self.par.append({"code": "number_page", "value": 3})

    # ------------------------------------------------------------------
    # Вспомогательные методы извлечения данных из HTML
    # ------------------------------------------------------------------

    @staticmethod
    def _page_url(page):
        """Возвращает URL страницы новостей (первая страница — без /page/)."""
        return NEWS_URL if page <= 1 else f'{NEWS_URL}/page/{page}'

    @staticmethod
    def _extract_url(item):
        """Извлекает абсолютный URL новости из элемента div.hentry."""
        # Атрибут data-url присутствует у крупных карточек
        data_url = item.get('data-url', '').strip()
        if data_url:
            return BASE_URL + data_url
        # Для мелких новостей — из тега <a itemprop="url">
        a_tag = item.find('a', itemprop='url')
        if a_tag:
            href = a_tag.get('href', '').strip()
            if href:
                return BASE_URL + href if href.startswith('/') else href
        return None

    @staticmethod
    def _clean_kremlin_date(txt):
        """
        Нормализует дату kremlin.ru перед передачей в get_public_date.
        Пример: '13 марта 2026 года, 13:25' → '13 марта 2026 13:25'
        """
        txt = re.sub(r'\bгода\b', '', txt)
        txt = re.sub(r'\s+', ' ', txt).strip()
        return txt

    @staticmethod
    def _extract_date(item):
        """
        Извлекает дату публикации из div.hentry.

        Логика:
        - Если текст содержит относительную дату («2 дня назад») —
          используем атрибут datetime="YYYY-MM-DD".
        - Иначе очищаем текст от «года» и передаём в get_public_date.
        """
        time_tag = item.find('time', itemprop='datePublished')
        if not time_tag:
            return ''
        txt = time_tag.get_text(strip=True)
        # Относительная дата («2 дня назад», «минуту назад» и т.п.)
        if 'назад' in txt or not txt:
            dt_attr = time_tag.get('datetime', '')
            return dt_attr  # YYYY-MM-DD — допустимый формат для БД
        return common.get_public_date(KremlinRu._clean_kremlin_date(txt))

    @staticmethod
    def _extract_title(item):
        """Извлекает заголовок новости из span[itemprop=name]."""
        span = item.find('span', itemprop='name')
        return span.get_text(strip=True) if span else ''

    @staticmethod
    def _collect_items(soup):
        """
        Возвращает список уникальных div.hentry (без дублей desktop/mobile).
        Дубли возникают из-за блоков hide-mobile / hide-desktop.
        """
        items = []
        seen = set()
        for item in soup.find_all('div', class_='hentry'):
            url = KremlinRu._extract_url(item)
            if url and url not in seen:
                seen.add(url)
                items.append(item)
        return items

    # ------------------------------------------------------------------
    # Разбор элемента новости
    # ------------------------------------------------------------------

    def make_values_init(self, rss, item):
        """
        Предварительный (лёгкий) разбор: только ссылка и дата.
        Используется для быстрой проверки наличия в БД.
        """
        self.global_count += 1
        rss['count'] += 1
        values = {
            'rss':         rss['id'],
            'url':         self._extract_url(item),
            'public_date': self._extract_date(item),
        }
        return values

    def make_values(self, rss, item):
        """
        Полный разбор элемента: заголовок, ссылка, дата.
        Переводит заголовок на ru/en/he.
        """
        values = {
            'rss':              rss['id'],
            'lang':             rss['lang'],
            'error_translator': False,
            'url':              self._extract_url(item),
            'public_date':      self._extract_date(item),
            'at_date_time':     datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        txt = self._extract_title(item)
        if txt:
            err, values['title_ru'], values['title_en'], values['title_he'] = (
                translate.make_translate(txt, values['lang']))
            values['error_translator'] = err
        return values

    # ------------------------------------------------------------------
    # Основной рабочий метод
    # ------------------------------------------------------------------

    def work(self):
        """
        Основной рабочий метод потока.
        Загружает параметры, авторизуется и последовательно парсит страницы.
        """
        super(KremlinRu, self).work()

        if common.get_value_config_param('active', self.par) != 1:
            self.finish_text = 'Поток не АКТИВЕН (active)'
            return True

        self.number_page = common.get_value_config_param('number_page', self.par) + 1
        result, self.rss = common.load_rss(self.rss_id, self.source)
        if not result:
            return result

        result, self.rss_themes = common.load_list_themes(self.source)
        if not result:
            return result

        result = self.make_login()
        if not result or self.rss.get('stop') is True:
            return result

        common.write_log_db(
            '✈️Start', SRC,
            f"Начало работы по опросу kremlin.ru ID={self.rss['id']}\n{self.description}",
            law_id=self.rss['sh_name'] + '\n' + self.source, page=self.rss['id'])

        if not self.rss_themes:
            self.finish_text = "❗Отсутствуют поисковые образы для kremlin.ru"
            return True

        # Инициализация счётчиков
        self.global_count = 0
        self.global_new = 0
        self.global_error = 0
        self.rss['count'] = 0
        self.rss['count_new'] = 0
        self.number = 0

        # Создаём сессию с прогревом главной страницы (cookies, Referer)
        session = requests.Session()
        session.mount(self.url, http_adapter)
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        })
        try:
            session.get(self.url, timeout=(10, 15))
        except Exception:
            pass  # прогрев необязателен — продолжаем без него

        # Обход страниц от number_page до 1 (от новых к старым)
        while self.number_page > 0:
            if self.number_page > 1:
                time.sleep(2)  # пауза между страницами — снижаем риск бана

            page_url = self._page_url(self.number_page)
            referer = self._page_url(self.number_page + 1) if self.number_page > 1 else self.url
            session.headers.update({"Referer": referer})

            try:
                r = session.get(page_url, timeout=(15, 30))
            except Exception as er:
                common.write_log_db(
                    '❌error', SRC,
                    f"Исключение при запросе страницы {self.number_page}: {er}\n{traceback.format_exc()}",
                    law_id=self.rss['sh_name'] + '\n' + self.source)
                self.global_error += 1
                break

            self.is_error = not r.ok
            if not r.ok:
                level = '❗warning' if r.status_code in (403, 429) or r.status_code >= 500 else '❌error'
                common.write_log_db(
                    level, SRC,
                    f"work\nОшибка {r.status_code} {r.reason} при запросе {page_url}",
                    law_id=self.rss['sh_name'] + '\n' + self.source)
                self.global_error += 1
                self.status_code = r.status_code
                break

            self.status_code = 0
            items = self._collect_items(BeautifulSoup(r.text, 'lxml'))

            for i, item in enumerate(items):
                try:
                    self.number += 1
                    values = self.make_values_init(self.rss, item)
                    if not values.get('url'):
                        continue

                    exist = common.is_exist_object(values, self.token)
                    if exist is not None and not exist:
                        # Новость ещё не в БД — полный разбор с переводом
                        values = self.make_values(self.rss, item)
                        common.seek(self.rss_themes, values)
                        is_article = translate.load_article(values)
                        if not values['themes'] and is_article:
                            common.seek_article(self.rss_themes, values)
                        if values['themes']:
                            ok_write = common.write_history(values, self.token, self.rss, self.source)
                            if ok_write:
                                self.global_new += 1
                                themes = ''
                                for theme in values['themes']:
                                    themes = themes + ', ' if themes else themes
                                    themes += common.get_name_theme(self.rss_themes, theme)
                                common.make_tg(self.source, themes, values, self.rss, i, len(items))
                                for theme in values['themes']:
                                    common.make_theme(theme, values, self.source, self.token)
                                if is_article:
                                    cloud.save_file_bucket('en_' + str(values['id']), values['text_en'])
                                    cloud.save_file_bucket('ru_' + str(values['id']), values['text_ru'])
                                    cloud.save_file_bucket('he_' + str(values['id']), values['text_he'])

                    # Помечаем как обработанную (в т.ч. если уже была в БД)
                    exists = common.is_exist_object(values, self.token)
                    if exists is not None and not exists:
                        common.fix_new(values, self.token)

                except Exception as er:
                    common.write_log_db(
                        '❌error', SRC,
                        f'work\ni={i + 1} из {len(items)}'
                        f"\nОшибка {er}\n{traceback.format_exc()}"
                        f"\nОбработка новости с сайта\n\n{page_url}\nkremlin_ru.work",
                        law_id=self.rss['sh_name'] + '\n' + self.source,
                        td=time.time() - self.t0)

            # Сохраняем номер текущей страницы в конфиг
            common.set_value_config_param(
                'number_page', self.par, self.number_page,
                token_admin=self.token, code_function=self.code_function)
            self.number_page -= 1

        self.finish_text = (
            f"{'➕' if self.global_new else ''}Получено новостей {self.global_count}, "
            f"записано {self.global_new}, ошибок {self.global_error}"
        )
        return True


if __name__ == "__main__":
    KremlinRu(
        'kremlin_ru', 'kremlin_ru', 'period',
        'Поток "Поиск тем в новостях kremlin.ru"',
        37  # ID записи в nsi_rss_list для kremlin.ru
    ).start()
    while True:
        time.sleep(5)
