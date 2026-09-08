"""
Парсер новостей с сайта 9-го ТВ канала Израиля (9tv.co.il).

Скрейпит страницы новостей, проверяет на наличие поисковых образов,
переводит найденные совпадения на три языка и записывает в БД и облако.
"""
from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
import datetime
import time
import common
from common import SRC
import trafaret_thread
import cloud
import translate

# Адаптер с автоповтором запросов (до 10 попыток при сетевых ошибках)
http_adapter = HTTPAdapter(max_retries=10)


class TV9coIl(trafaret_thread.TrafaretThread):
    """
    Поток парсинга новостей с сайта 9tv.co.il.

    Перебирает страницы новостей (по 9 на странице), для каждой проверяет
    наличие в БД, ищет поисковые образы, переводит и записывает.
    """
    # Неизменяемые значения по умолчанию (безопасно на уровне класса)
    global_new = 0            # кол-во новых записанных новостей за цикл
    global_error = 0          # кол-во ошибок за цикл
    number_page = None        # номер текущей страницы новостей
    url = 'https://www.9tv.co.il/'
    url_news = url + 'allnews/'
    # FIX: удалены list_rss = list() (мёртвый код, нигде не использовался)
    # FIX: удалён rss = None (конфликтовал с self.rss = {} из родительского __init__;
    #       родительский run() вызывает self.rss.get(), что падало на None)

    def __init__(self, source, code_function, code_period, description, rss_id):
        self.rss_id = rss_id
        # FIX: Изменяемый атрибут — на уровне экземпляра
        # (list на уровне класса разделяется между всеми экземплярами!)
        self.rss_themes = []
        super(TV9coIl, self).__init__(source, code_function, code_period, description)

    def initiation_parameters(self):
        """Задаёт параметры по умолчанию: период опроса (10 мин) и активность."""
        super(TV9coIl, self).initiation_parameters()
        self.par.append({"code": "period", "value": 10})
        self.par.append({"code": "active", "value": 1})

    def make_values_init(self, rss, new):
        """
        Предварительный (лёгкий) разбор элемента новости: только ссылка и дата.
        Используется для быстрой проверки — существует ли новость уже в БД.
        """
        self.global_count += 1
        rss['count'] += 1
        values = dict()
        values["rss"] = rss['id']

        # Ссылка на источник
        values['url'] = self.url + new.find('a', class_='item_landscape_link').attrs['href'][1:]
        new_content = new.find('div', class_='item_info_gr')

        # Дата публикации
        txt = new_content.find('div', class_='item_info_date').text
        if txt:
            values['public_date'] = common.get_public_date(txt)
        return values

    def make_values(self, rss, new):
        """
        Полный разбор элемента новости: заголовок, описание, дата.
        Переводит тексты на три языка (ru, en, he).
        """
        values = dict()
        values["rss"] = rss['id']
        values["lang"] = rss['lang']  # FIX: было "{lang}".format(lang=rss['lang']) — избыточно

        # Ссылка на источник
        values['url'] = self.url + new.find('a', class_='item_landscape_link').attrs['href'][1:]
        new_content = new.find('div', class_='item_info_gr')

        # Заголовок новости
        txt = new_content.find('h2', class_='item_sm_title').text
        values['error_translator'], values['title_ru'], values['title_en'], values['title_he'] = (
            translate.make_translate(txt, values["lang"]))

        # Текст/описание новости
        txt = new_content.find('div', class_='txt_news').text
        error, values['description_ru'], values['description_en'], values['description_he'] = (
            translate.make_translate(txt, values["lang"]))
        values['error_translator'] = values['error_translator'] or error

        # Дата публикации
        txt = new_content.find('div', class_='item_info_date').text
        if txt:
            values['public_date'] = common.get_public_date(txt)

        # Дата и время записи новости в БД (UTC)
        # FIX: было "{date}".format(date=str(datetime.datetime.utcnow())) — тройная избыточность
        # str() + .format() + utcnow() deprecated в Python 3.12+
        values["at_date_time"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return values

    def work(self):
        """
        Основной рабочий метод потока.
        Загружает параметры, авторизуется и последовательно парсит страницы новостей.
        """
        super(TV9coIl, self).work()
        if common.get_value_config_param('active', self.par) != 1:
            self.finish_text = 'Поток не АКТИВЕН (active)'
            return True
        self.number_page = common.get_value_config_param('number_page', self.par) + 1
        result, self.rss = common.load_rss(self.rss_id, self.source)
        self.law_id = self.rss['sh_name']
        if result:
            result, self.rss_themes = common.load_list_themes(self.source)
            if result:
                result = self.make_login()
                # FIX: .get('stop') вместо ['stop'] — защита от KeyError
                if result and self.rss.get('stop') != True:
                    common.write_log_db(
                        '✈️Start', SRC,
                        f"Начало работы по опросу ленты новостей tv9co_il ID={self.rss['id']}\n{self.description}",
                        law_id=self.source, page=self.number_page)
                    if len(self.rss_themes) == 0:
                        self.finish_text = "❗Отсутствуют поисковые образы для новостных каналов"
                        return True
                    else:
                        self.global_count = 0
                        self.global_new = 0
                        self.global_error = 0
                        self.rss['count'] = 0
                        self.rss['count_new'] = 0
                        self.rss['count_error'] = 0
                        self.number = 0
                        session = requests.Session()
                        session.mount(self.url_news, http_adapter)
                        session.headers.update({
                            "User-Agent": (
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/124.0.0.0 Safari/537.36"
                            ),
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
                        })
                        # Сначала загружаем главную страницу новостей — получаем cookies
                        # и устанавливаем правильный Referer для последующих запросов
                        referer = self.url_news
                        try:
                            session.get(self.url, timeout=(10, 10))
                        except Exception:
                            pass
                        while self.number_page > 0:
                            if self.number_page > 1:
                                time.sleep(2)  # пауза между страницами — снижает риск 403
                            session.headers.update({"Referer": referer})
                            page_url = self.url_news + str(self.number_page)
                            r = session.get(page_url, timeout=(100, 100))
                            referer = page_url  # следующий запрос ссылается на текущую страницу
                            self.is_error = not r.ok
                            if r.ok:
                                self.status_code = 0
                                news = BeautifulSoup(r.text, 'lxml').find_all('li', class_='half_list_item')
                                for i, new in enumerate(news):
                                    # FIX: добавлен try/except для каждой новости
                                    # (раньше одна ошибка ломала обработку всей страницы)
                                    try:
                                        self.number += 1
                                        # Предварительный разбор — проверка на дубликат
                                        values = self.make_values_init(self.rss, new)
                                        exist = common.is_exist_object(values, self.token)
                                        if exist is not None and not exist:
                                            # Новость ещё не в БД — полный разбор с переводом
                                            values = self.make_values(self.rss, new)
                                            common.seek(self.rss_themes, values)  # поиск поисковых образов
                                            is_article = translate.load_article(values)
                                            # Если образы не найдены в заголовке — ищем в тексте статьи
                                            if len(values['themes']) == 0 and is_article:
                                                common.seek_article(self.rss_themes, values)
                                            if values['themes']:  # есть совпадения
                                                ok_write = common.write_history(values, self.token, self.rss, self.source)
                                                if ok_write:
                                                    # Формирование строки тем для Telegram
                                                    themes = ''
                                                    self.global_new += 1
                                                    for theme in values['themes']:
                                                        themes = themes + ', ' if themes else themes
                                                        themes += common.get_name_theme(self.rss_themes, theme)
                                                    common.make_tg(self.source, themes, values, self.rss, i, len(news))
                                                    # Запись связей тема <-> новость
                                                    for theme in values['themes']:
                                                        common.make_theme(theme, values, self.source, self.token)
                                                    # Сохранение переведённых текстов в облако
                                                    if is_article:
                                                        cloud.save_file_bucket('en_' + str(values['id']), values['text_en'])
                                                        cloud.save_file_bucket('ru_' + str(values['id']), values['text_ru'])
                                                        cloud.save_file_bucket('he_' + str(values['id']), values['text_he'])
                                        # Помечаем новость как обработанную
                                        exists = common.is_exist_object(values, self.token)
                                        if exists is not None and not exists:
                                            common.fix_new(values, self.token)
                                    except Exception as er:
                                        common.write_log_db(
                                            '❌error', SRC,
                                            f'i={i+1} из {len(news)}'
                                            f"\nОшибка {er}\nОбработка новости с сайта\n\n{self.url_news}"
                                            f"\ntv9co_il.work",
                                            law_id=self.source,
                                            td=time.time() - self.t0)
                                common.set_value_config_param('number_page', self.par, self.number_page,
                                                              token_admin=self.token, code_function=self.code_function)
                                self.number_page -= 1
                            else:
                                # FIX: было print() — debug-вывод в продакшене; заменён на write_log_db
                                level = '❌error'
                                if int(r.status_code) in [403] or int(r.status_code) >= 500:
                                    level = '❗warning'
                                common.write_log_db(
                                    level, SRC,
                                    f"work\nОшибка {r.status_code} {r.reason} при запросе страницы {self.number_page}",
                                    law_id=self.source)
                                self.global_error += 1
                                self.status_code = r.status_code
                                break
                        self.finish_text = (
                                f"{'➕' if self.global_new else ''}Получено новостей {self.global_count}, "
                                f"записано {self.global_new}, ошибок {self.global_error}\n"
                            )
                        return True
        return result


if __name__ == "__main__":
    TV9coIl('tv9co_il', 'tv9co_il', 'period', 'Поток "Поиск тем в новостях 9-го ТВ канала Израиля"', 33).start()
    while True:
        time.sleep(5)
