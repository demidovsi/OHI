"""
Считывание ленты новостей из списка сайтов в формате RSS.
Анализ наличия заданных поисковых образов в новостях лент и запись таких новостей в БД с трансляцией на три языка.
Чтение текста статьи по url из новости, перевод на три языка и запись текстов в облако.
"""
import asyncio
import datetime
import certifi
import html as html_module
import locale
import re
import sys
import threading
from pathlib import Path
from urllib.parse import urlparse

import trafaret_thread
import common
from common import SRC
import requests
import xml.etree.ElementTree as ET
import time
import cloud
import translate

try:
    from curl_cffi import requests as curl_requests
except Exception:
    curl_requests = None

try:
    from playwright.async_api import async_playwright as _pw_async_playwright
    _playwright_available = True
except Exception:
    _playwright_available = False

try:
    from playwright_stealth import stealth_async as _stealth_async
    _stealth_available = True
except Exception:
    _stealth_available = False

# Семафор ограничивает число одновременных запусков Playwright:
# каждый headless Chromium занимает ~250 МБ RAM.
_playwright_semaphore = threading.Semaphore(2)

# FIX: Установка локали один раз при загрузке модуля.
# locale.setlocale() изменяет состояние ВСЕГО процесса и не является потокобезопасной.
# Вызывать её в цикле обработки каждой новости — опасно в многопоточной среде.
locale.setlocale(locale.LC_ALL, '')

# Именованные HTML-сущности, которые невалидны в XML (только &amp;/&lt;/&gt;/&quot;/&apos; — валидны).
# Заменяем их на числовые ссылки, которые XML понимает.
_HTML_ENTITY_RE = re.compile(r'&(?!amp;|lt;|gt;|quot;|apos;|#)([a-zA-Z][a-zA-Z0-9]*);')


def _parse_xml(content):
    """
    Парсит RSS/XML из bytes или str.
    При ошибке 'invalid token' (HTML-сущности) заменяет именованные сущности
    на числовые Unicode-ссылки и повторяет попытку.
    """
    try:
        if isinstance(content, str):
            content = content.encode('utf-8')
        return ET.fromstring(content)
    except ET.ParseError:
        text = content.decode('utf-8', errors='replace') if isinstance(content, bytes) else content
        # Заменяем &nbsp; → &#160; и т.п. через html.unescape + обратное экранирование
        fixed = _HTML_ENTITY_RE.sub(
            lambda m: '&#{};'.format(ord(html_module.unescape('&{};'.format(m.group(1))))), text
        )
        return ET.fromstring(fixed.encode('utf-8'))


# --- HTTP-заголовки для запросов RSS-лент ---

# Основные заголовки, имитирующие браузер (подходят для большинства сайтов).
# Referer здесь отсутствует — он добавляется динамически в get_url()
# на основе домена запрашиваемого URL, что имитирует переход внутри сайта.
# Accept-Language нейтральный (en-US): Hebrew-first ломал российские/немецкие сайты.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "DNT": "1",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
}

# Минимальные заголовки (curl-подобные) — запасной вариант
CURL_HEADERS = {"User-Agent": "curl/8.5.0"}

# FIX: Удалены захардкоженные cookies и __token — они были привязаны к конкретной
# Cloudflare-сессии, давно истекли и не несли пользы (только шум и утечка данных).
# Заголовки для Windows-окружения
WINDOWS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Referer": "https://www.google.com/",
    "Pragma": "no-cache",
    "Sec-Ch-Ua": '"Not.A/Brand";v="8", "Chromium";v="114", "Google Chrome";v="114"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# Заголовки для Linux-окружения
LINUX_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Referer": "https://www.google.com/",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache"
}


def system_ca_bundle():
    """Определяет путь к системному CA-сертификату для HTTPS-запросов."""
    for p in (
            "/etc/ssl/certs/ca-certificates.crt",  # Debian/Ubuntu/Alpine
            "/etc/pki/tls/certs/ca-bundle.crt",    # RHEL/CentOS/Fedora
            "/etc/ssl/cert.pem",                    # Arch/macOS
    ):
        if Path(p).exists():
            return p
    try:
        return certifi.where()  # запасной вариант — библиотека certifi
    except Exception:
        return True  # пусть requests решит сам


async def _fetch_rss_playwright(url):
    """
    Загружает RSS/XML-ленту через Playwright (headless Chromium).

    Стратегия:
    1. Запуск с анти-детекцией: navigator.webdriver скрыт (иначе DDoSGuard не выполняет JS).
    2. goto(domcontentloaded) → challenge-страница.
    3. Опрос каждые 1с (макс 15с): ждём пока challenge-маркеры исчезнут из текста страницы.
    4. Попытка A: fetch() внутри страницы (cookies прикладываются автоматически).
    5. Попытка Б: cookies из браузера + curl_cffi с TLS-имитацией Chrome.
    """
    async with _pw_async_playwright() as pw:
        launch_args = ['--disable-blink-features=AutomationControlled']
        if sys.platform.startswith('linux'):
            # На Linux (особенно под root/Docker) Chromium требует отключения sandbox
            launch_args += ['--no-sandbox', '--disable-setuid-sandbox']
        browser = await pw.chromium.launch(
            headless=True,
            args=launch_args
        )
        try:
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                )
            )
            # Скрываем navigator.webdriver — DDoSGuard проверяет этот флаг
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page = await context.new_page()
            # playwright-stealth: полная маскировка под реальный Chrome (plugins, WebGL, etc.)
            if _stealth_available:
                await _stealth_async(page)

            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=15000)
            except Exception:
                pass

            # Ждём завершения DDoSGuard JS-challenge (обычно ~5 сек).
            # Опрашиваем каждую секунду — выходим, когда challenge-маркеры исчезнут.
            _challenge_marks = ('ddos-guard', 'ожидайте', 'checking your browser')
            for _ in range(15):
                await asyncio.sleep(1)
                try:
                    body = await page.evaluate("document.body?.innerText || ''")
                    if not any(m in body.lower() for m in _challenge_marks):
                        break  # challenge пройден, страница сменилась
                except Exception:
                    break  # навигация в процессе — выходим

            # Ждём загрузки DOM после редиректа
            try:
                await page.wait_for_load_state('domcontentloaded', timeout=10000)
            except Exception:
                pass

            xml_bytes = None

            # Попытка A: fetch() из контекста страницы (cookies прикладываются автоматически)
            try:
                xml_text = await page.evaluate(
                    """async (u) => {
                        try {
                            const r = await fetch(u, {credentials: 'include'});
                            if (r.ok) return await r.text();
                        } catch (e) {}
                        return null;
                    }""",
                    url
                )
                if xml_text and len(xml_text) > 100:
                    xml_bytes = xml_text.encode('utf-8')
            except Exception:
                pass

            # Попытка Б: собираем cookies из браузера → curl_cffi с имитацией Chrome TLS
            if xml_bytes is None and curl_requests is not None:
                try:
                    cookies = await context.cookies()
                    cookie_dict = {c['name']: c['value'] for c in cookies}
                    r = curl_requests.get(
                        url,
                        cookies=cookie_dict,
                        impersonate='chrome120',
                        timeout=20
                    )
                    if r.ok:
                        xml_bytes = r.content
                except Exception:
                    pass

            # Попытка В: читаем контент страницы напрямую — после challenge RSS-лента и есть XML
            if xml_bytes is None:
                try:
                    page_content = await page.content()
                    if page_content and '<item' in page_content:
                        xml_bytes = page_content.encode('utf-8')
                except Exception:
                    pass

            await context.close()
        finally:
            await browser.close()

    return xml_bytes


class SearchRSS(trafaret_thread.TrafaretThread):
    """
    Поток поиска новостей по RSS-лентам.

    Загружает RSS-ленту, проверяет каждую новость на наличие поисковых образов,
    переводит найденные совпадения на три языка и записывает в БД и облако.
    """

    def __init__(self, source, code_function, code_period, description, rss_id):
        self.print_load = False
        self.rss_id = rss_id
        # FIX: Изменяемый атрибут — на уровне экземпляра
        # (list на уровне класса разделяется между всеми экземплярами!)
        self.rss_themes = []
        super(SearchRSS, self).__init__(source, code_function, code_period, description)

    def initiation_parameters(self):
        """Задаёт параметры по умолчанию: период опроса (10 мин) и активность."""
        super(SearchRSS, self).initiation_parameters()
        self.par.append({"code": "period", "value": 10})
        self.par.append({"code": "active", "value": 1})

    def make_values(self, rss, item):
        """
        Полный разбор элемента RSS-ленты: заголовок, ссылка, описание, автор, дата.
        Переводит тексты на три языка (ru, en, he).
        Возвращает словарь values с данными новости.
        """
        values = dict()
        values["rss"] = rss['id']
        values["lang"] = rss['lang']  # FIX: было "{lang}".format(lang=rss['lang']) — избыточно
        values['error_translator'] = False

        # Заголовок новости (title или HEADLINE для нестандартных форматов)
        if item.find('title') is not None:
            txt = common.extract_text(item.find('title'))
            err, values['title_ru'], values['title_en'], values['title_he'] = translate.make_translate(txt, values["lang"])
        elif item.find('HEADLINE') is not None:
            txt = common.extract_text(item.find('HEADLINE'))
            err, values['title_ru'], values['title_en'], values['title_he'] = translate.make_translate(txt, values["lang"])

        # Ссылка на источник (link или URL)
        txt = None
        if item.find('link') is not None:
            txt = common.extract_text(item.find('link'))
        elif item.find('URL') is not None:
            txt = common.extract_text(item.find('URL'))
        if txt:
            values["url"] = txt  # FIX: было "{txt}".format(txt=txt) — избыточно

        # Текст/описание новости (description или ABSTRACT)
        txt = ''
        if item.find('description') is not None:
            txt = common.extract_text(item.find('description'))
        elif item.find('ABSTRACT') is not None:
            txt = common.extract_text(item.find('ABSTRACT'))
        if txt:
            description = cloud.make_description(txt)
            error, values['description_ru'], values['description_en'], values['description_he'] = (
                translate.make_translate(description, values["lang"]))
            values['error_translator'] = values['error_translator'] or error

        # Автор новости
        txt = common.extract_text(item.find('author'))
        if txt:
            values['author'] = txt  # FIX: было "{txt}".format(txt=txt) — избыточно
        else:
            txt = common.extract_text(item.find('creator'))
            if txt:
                values['author'] = txt  # FIX: было "{txt}".format(txt=txt) — избыточно

        # Категории новости — добавляем к автору через " | "
        item_cats = [common.extract_text(cat) for cat in item.findall('category')]
        item_cats = [c for c in item_cats if c]
        if item_cats:
            cats_str = ', '.join(item_cats)
            values['author'] = (values['author'] + ' | ' + cats_str) if values.get('author') else cats_str

        # Полный текст из RSS-ленты (rbc_news:full-text, content:encoded и аналоги)
        for child in item:
            local = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            if local in ('full-text', 'encoded'):
                raw = common.extract_text(child)
                if raw:
                    values['full_text_rss'] = raw
                    break

        # Дата публикации новости
        # FIX: locale.setlocale() убран отсюда — вызывается один раз при загрузке модуля
        txt = common.extract_text(item.find('pubDate'))
        if txt:
            values['public_date'] = common.get_public_date(txt)
        else:
            values['public_date'] = ''

        # Дата и время записи новости в БД (UTC)
        # FIX: utcnow() deprecated в Python 3.12+, заменён на now(timezone.utc)
        values["at_date_time"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return values

    def make_values_init(self, rss, item):
        """
        Предварительный (лёгкий) разбор элемента RSS: только ссылка и дата.
        Используется для быстрой проверки — существует ли новость уже в БД.
        """
        rss['count'] += 1
        values = dict()
        values["rss"] = rss['id']

        # Ссылка на источник
        txt = None
        if item.find('link') is not None:
            txt = common.extract_text(item.find('link'))
        elif item.find('URL') is not None:
            txt = common.extract_text(item.find('URL'))
        if txt:
            values["url"] = txt  # FIX: было "{txt}".format(txt=txt) — избыточно

        # Дата публикации
        # FIX: locale.setlocale() убран отсюда — вызывается один раз при загрузке модуля
        txt = common.extract_text(item.find('pubDate'))
        if txt:
            values['public_date'] = common.get_public_date(txt)
        else:
            values['public_date'] = ''

        return values

    def get_url(self, rss):
        """
        Загружает и парсит RSS-ленту по URL с несколькими попытками и разными заголовками.

        Стратегия:
        1. curl_cffi с impersonate=chrome124/120/firefox121 (обходит TLS-fingerprinting / WAF)
        2. Основной запрос с BROWSER_HEADERS + динамический Referer
        3. До max_retries попыток с разными наборами заголовков + экспоненциальная задержка
        4. Playwright (headless Chromium) — решает JS-challenge DDoSGuard/Cloudflare

        Возвращает (xml_root, True) при успехе или (error_message, False) при неудаче.
        """
        max_retries = 3
        initial_delay = 2  # начальная задержка в секундах
        response = None
        current_delay = initial_delay
        st_er = ''
        url = rss['url']
        # Windows UA блокируется значительно реже, чем Linux UA (антибот-системы).
        # Поэтому на Linux тоже предпочитаем Windows-заголовки как основные.
        platform_headers = WINDOWS_HEADERS
        alt_headers = LINUX_HEADERS
        # Динамический Referer: имитируем переход внутри того же сайта.
        # Статичный Referer (особенно чужой домен) — частая причина 403.
        _parsed = urlparse(url)
        _site_url = f"{_parsed.scheme}://{_parsed.netloc}/"
        browser_headers = {**BROWSER_HEADERS, "Referer": _site_url}
        try:
            # Попытка 0: curl_cffi с имитацией TLS-отпечатка Chrome (обходит WAF/403).
            # Пробуем несколько версий браузера — разные WAF блокируют разные отпечатки.
            if curl_requests is not None:
                for _imp in ('chrome124', 'chrome120', 'firefox121'):
                    try:
                        r = curl_requests.get(url, impersonate=_imp, timeout=20)
                        if r.ok:
                            result = _parse_xml(r.content)
                            self.status_code = 0
                            return result, True
                        if not st_er:
                            st_er = f'{r.status_code} {r.reason} (curl_cffi/{_imp})\n'
                    except Exception as err:
                        if not st_er:
                            st_er = f'curl_cffi/{_imp}: {err}\n'

            # Первая попытка с основными заголовками (динамический Referer)
            try:
                response = requests.get(url, headers=browser_headers, timeout=20)
                if response.ok:
                    result = _parse_xml(response.content)
                    self.status_code = 0
                    return result, True
                if not st_er:
                    self.status_code = response.status_code
                    st_er = f'{response.status_code} {response.reason}\n'
            except Exception as err:
                if not st_er:
                    st_er = f'{err}\n'

            # Повторные попытки с разными наборами заголовков
            for attempt in range(max_retries):
                verify_path = system_ca_bundle()
                try:
                    # Попытка с платформенными заголовками
                    response = requests.get(url, headers=platform_headers, timeout=20, verify=verify_path)

                    # Альтернативные заголовки (другая платформа)
                    if not response.ok:
                        response.close()
                        response = requests.get(url, headers=alt_headers, timeout=20, verify=verify_path)

                    # Минимальные (curl) заголовки
                    if not response.ok:
                        response.close()
                        response = requests.get(url, headers=CURL_HEADERS, timeout=20, verify=verify_path)

                    current_delay = initial_delay * (2 ** attempt)  # экспоненциальная задержка

                    # Обработка 429 Too Many Requests — ждём указанное сервером время
                    if response.status_code == 429:
                        retry_after = response.headers.get('Retry-After')
                        wait_time = int(retry_after) if retry_after and retry_after.isdigit() else current_delay
                        time.sleep(wait_time)

                    if response.ok:
                        result = _parse_xml(response.content)
                        self.status_code = 0
                        return result, True
                    else:
                        if not st_er:
                            self.status_code = response.status_code
                            st_er = f'{response.status_code} {response.reason}\n'

                    # Для ошибок кроме 429 — дополнительные стратегии
                    if response.status_code != 429:
                        response.close()
                        # Запрос без заголовков
                        response = requests.get(url, timeout=10)
                        if response.ok:
                            result = _parse_xml(response.content)
                            self.status_code = 0
                            return result, True

                        # Запрос через сессию (с поддержкой cookies/redirect)
                        response.close()
                        with requests.Session() as session:
                            response = session.get(url, timeout=10)
                        if response.ok:
                            result = _parse_xml(response.content)
                            self.status_code = 0
                            return result, True

                    # FIX: было attempt < max_retries — sleep после ПОСЛЕДНЕЙ попытки бессмыслен
                    if attempt < max_retries - 1:
                        time.sleep(current_delay)

                except Exception as err:
                    if not st_er:
                        st_er = f'{err}\n'
                    time.sleep(current_delay)

            # Попытка через Playwright: рендерит JS-challenge (DDoSGuard, Cloudflare).
            # При 429 (rate limit) Playwright не поможет — сервер ограничивает по IP/токену.
            # Семафор ограничивает число одновременных Chromium-процессов (каждый ~250 МБ).
            if _playwright_available and self.status_code != 429:
                with _playwright_semaphore:
                    try:
                        xml_bytes = self._async_loop.run_until_complete(_fetch_rss_playwright(url))
                        if xml_bytes:
                            result = _parse_xml(xml_bytes)
                            self.status_code = 0
                            return result, True
                        st_er += 'playwright: XML не получен\n'
                    except Exception as err:
                        if "Executable doesn" in str(err):
                            # Браузер не установлен — скачаем и повторим
                            import subprocess, sys
                            subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'])
                            try:
                                xml_bytes = self._async_loop.run_until_complete(_fetch_rss_playwright(url))
                                if xml_bytes:
                                    result = _parse_xml(xml_bytes)
                                    self.status_code = 0
                                    return result, True
                                st_er += 'playwright: XML не получен\n'
                            except Exception as err2:
                                st_er += f'playwright: {err2}\n'
                        else:
                            st_er += f'playwright: {err}\n'

            # Все попытки исчерпаны
            result = (f"После {max_retries} попыток не удалось получить RSS-ленту. Возможно, "
                      f"сервер перегружен или заблокировал доступ.\n\n") + st_er
            if response:
                result += f'\n{response.status_code} {response.reason}'
            return result, False
        except Exception as err:
            import traceback
            self.status_code = 999
            result = f"Некорректность запроса: {err}\n{traceback.format_exc()}"
            return result, False

    def analyses_rss(self, rss):
        """
        Анализ одной RSS-ленты:
        1. Загрузка и парсинг ленты
        2. Для каждой новости — проверка на дубликат, поиск поисковых образов
        3. При совпадении — перевод, запись в БД и облако, уведомление в Telegram
        """
        t0 = time.time()
        url = rss['url']
        root, ok = self.get_url(rss)
        rss['count'] = 0
        rss['count_new'] = 0
        self.is_error = not ok
        if ok:
            # Поиск элементов новостей (стандартный item или CONTENTITEM для нестандартных RSS)
            items = root.findall('.//item')
            if len(items) == 0:
                items = root.findall('.//CONTENTITEM')
            self.global_count = len(items)
            for j, item in enumerate(items):
                try:
                    self.number = j + 1
                    # Фильтрация по категориям: если в настройках RSS заданы категории,
                    # пропускаем новость, у которой нет ни одной совпадающей <category>
                    categories_filter = rss.get('categories', '') or ''
                    if categories_filter:
                        allowed = {c.strip().lower() for c in categories_filter.split(',') if c.strip()}
                        item_cats = {common.extract_text(cat).lower() for cat in item.findall('category')}
                        item_cats.discard('')
                        if not allowed & item_cats:
                            continue
                    # Предварительный разбор — проверка, есть ли уже в БД
                    values = self.make_values_init(rss, item)
                    exist = common.is_exist_object(values, self.token)
                    if exist is not None and not exist:
                        # Новость ещё не в БД — полный разбор с переводом
                        values = self.make_values(rss, item)
                        common.seek(self.rss_themes, values)  # поиск вхождений поисковых образов
                        is_article = translate.load_article(values)
                        # Если образы не найдены в заголовке/описании — ищем в тексте статьи
                        if len(values['themes']) == 0 and is_article:
                            common.seek_article(self.rss_themes, values)
                        if values['themes']:  # есть совпадения с поисковыми образами
                            # Записать новость в БД
                            ok_write = common.write_history(values, self.token, rss, self.source)
                            if ok_write:  # новость записана в БД
                                # Формирование строки с названиями тем для Telegram
                                themes = ''
                                for theme in values['themes']:
                                    themes = themes + ', ' if themes else themes
                                    themes += common.get_name_theme(self.rss_themes, theme)
                                common.make_tg(self.source, themes, values, rss, j, self.global_count)  # уведомление в ТГ
                                # Запись связей тема <-> новость
                                for theme in values['themes']:
                                    common.make_theme(theme, values, self.source, self.token)
                                # Сохранение переведённых текстов статьи в облако
                                if is_article:
                                    cloud.save_file_bucket('en_' + str(values['id']), values['text_en'])
                                    cloud.save_file_bucket('ru_' + str(values['id']), values['text_ru'])
                                    cloud.save_file_bucket('he_' + str(values['id']), values['text_he'])
                    # Помечаем новость как обработанную (в т.ч. если уже существовала)
                    exists = common.is_exist_object(values, self.token)
                    if exists is not None and not exists:
                        common.fix_new(values, self.token)
                except Exception as er:
                    import traceback as _tb
                    common.write_log_db(
                        '❌error', SRC,
                        f'j={j+1} из {len(items)}'
                        f"\nОшибка {er}\n{_tb.format_exc()}\nОбработка новости с сайта\n\n{url}\nanalyses_rss",
                        law_id=rss['sh_name'] + '\n' + self.source, td=time.time() - t0)
                time.sleep(0.5)
            del root, items  # XML-дерево и список элементов больше не нужны — освобождаем память
            st_new = '➕ ' if rss['count_new'] else ''
            self.finish_text += (
                f'Закончена обработка новостной ленты сайта "{rss["sh_name"]}" (ID={rss["id"]}); '
                f'новостей={self.global_count};\n{st_new}записано={rss["count_new"]}; обработано={rss["count"]}'
            )
            return True
        else:
            # Ошибка загрузки ленты — классифицируем и логируем
            st = '❗Много запросов' if '429 Too Many' in str(root) else (
                        '❗Запрет чтения' if '403 Forbidden' in str(root) else '⚠️requests'
                    )
            mes = f"Внимание {st}\n{root}\nЗапрос ленты новостей с сайта\n\n{url}"
            common.write_log_db(st, SRC, mes, page=rss['id'], law_id=rss['sh_name'] + '\n' + self.source, td=time.time() - self.t0)
            return False

    def work(self):
        """
        Основной рабочий метод потока.
        Загружает параметры RSS, авторизуется и запускает анализ ленты.
        """
        super(SearchRSS, self).work()
        if common.get_value_config_param('active', self.par) != 1:
            return False
        result, self.rss = common.load_rss(self.rss_id, self.source)
        self.law_id = self.rss['sh_name']

        if result:
            result, self.rss_themes = common.load_list_themes(self.source)
            if result:
                result = self.make_login()
                if result and self.rss['stop'] != True:
                    common.write_log_db('✈️Start', SRC,
                                        f"Начало работы по опросу ленты новостей с сайта [{self.rss['sh_name']}] ID={self.rss['id']}",
                                        page=self.rss['id'], law_id=self.rss['sh_name'] + '\n' + self.source)
                    if len(self.rss_themes) == 0:
                        self.finish_text = "Отсутствуют поисковые образы для сайтов с RSS"
                    else:
                        self.analyses_rss(self.rss)
                        return True  # повторить через заданный период даже если ошибка внутри анализа
                else:
                    return False  # повторить через 10 минут
        return result


if __name__ == "__main__":
    SearchRSS('SearchRSS', 'SearchRSS', 'period', 'Поток "Поиск тем в новостных лентах"', 51).start()
    while True:
        time.sleep(5)

"""
api_key=57cd04c607fb4839904f81cff3347bb3
"""