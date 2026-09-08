import html as html_module
import re
import time
import threading
from urllib.parse import urlparse

from deep_translator import GoogleTranslator
# from googletrans import Translator
from deep_translator.exceptions import TooManyRequests
import asyncio

import cloud
import TranslateManager
# newspaper, grab_article, hill_article — тяжёлые зависимости (NLTK, trafilatura, playwright).
# Импортируются лениво внутри load_article(), чтобы не грузить память при старте сервера.

# Thread-local персистентный event loop для asyncio.
# asyncio.run() создаёт/уничтожает loop на каждый вызов → фрагментация heap и утечки ProactorEventLoop (Windows).
# Персистентный loop переиспользуется в пределах одного потока — так же, как _async_loop в trafaret_thread.py.
_tls = threading.local()

# Минимальный интервал (сек) между последовательными запросами к одному домену.
# Защищает от блокировок по частоте обращений (429, временный бан).
ARTICLE_DOMAIN_DELAY = 5.0

_domain_last_request: dict = {}
_domain_lock = threading.Lock()


def _domain_throttle(url: str) -> None:
    """Выдерживает паузу ARTICLE_DOMAIN_DELAY между запросами к одному домену."""
    try:
        domain = urlparse(url).netloc
    except Exception:
        return
    with _domain_lock:
        wait = ARTICLE_DOMAIN_DELAY - (time.time() - _domain_last_request.get(domain, 0.0))
        if wait > 0:
            time.sleep(wait)
        _domain_last_request[domain] = time.time()


def _get_article_loop() -> asyncio.AbstractEventLoop:
    """Возвращает персистентный event loop текущего потока, создавая его при первом обращении."""
    if not hasattr(_tls, 'loop') or _tls.loop.is_closed():
        _tls.loop = asyncio.new_event_loop()
    return _tls.loop

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# Создание экземпляра TranslationManager
translator = TranslateManager.TranslationManager(max_retries=3, initial_delay=2, cooldown_period=60)


def get_array_text(text, limit=2000):
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
            while i > 0 and st[i] != '.':
                i -= 1
            result.append(st[:i+1])
            text = text[i+1:]
    return result


# def translate_text(text, target_lang='en'):
#     translator = Translator()
#     translated = translator.translate(text, dest=target_lang)
#     return translated.text


def make_translate(txt, init_lang):
    text = get_array_text(txt)
    text_ru = ''
    text_en = ''
    text_he = ''
    error_translator = False
    for unit in text:
        if init_lang == 'ru':
            text_ru += unit
        else:
            is_ok, res = translator.translate(unit, 'ru')
            text_ru += res or ''
            if not is_ok:
                error_translator = True

        if init_lang == 'en':
            text_en += unit
        else:
            is_ok, res = translator.translate(unit, 'en')
            text_en += res or ''
            if not is_ok:
                error_translator = True

        if init_lang == 'he':
            text_he += unit
        else:
            is_ok, res = translator.translate(unit, 'iw')
            text_he += res or ''
            if not is_ok:
                error_translator = True
    return error_translator, text_ru, text_en, text_he


_CHALLENGE_MARKERS = (
    'пожалуйста, ожидайте',       # DDoSGuard (RU)
    'проверка доступа к браузеру', # DDoSGuard (RU)
    'ddos-guard',                  # DDoSGuard (имя сервиса / домен)
    'checking your browser',       # DDoSGuard (EN)
    'just a moment',               # Cloudflare (EN)
    'checking if the site connection is secure',  # Cloudflare (EN)
    'enable javascript and cookies',              # Cloudflare (EN)
    "that's an error",             # генерическая страница ошибки Google (Error 404/500 !!1)
    "that's all we know",          # генерическая страница ошибки Google (Error 404/500 !!1)
    '404 not found',
    'the requested url was not found on this server',
    'если вы не бот, скопируйте отчет',  # анти-бот блокировка (напр. tass.ru)
)


def _is_challenge_page(text):
    """Возвращает True, если текст — не статья, а служебная страница
    (JS-challenge DDoSGuard/Cloudflare, генерическая страница ошибки и т.п.)."""
    low = text.lower().replace('’', "'")  # curly quote → straight quote
    return any(m in low for m in _CHALLENGE_MARKERS)


def load_article(values, init_lang='', delay=1):
    """
    Загружает текст статьи по URL и переводит на три языка.
    Цепочка попыток (каждая следующая — если предыдущая не дала текст):
      1) newspaper3k — быстрый, но часто получает 403
      2) hill_article — httpx HTTP/2, AMP-варианты, curl_cffi (лёгкий обход 403)
      3) grab_article — Playwright (тяжёлый, но надёжный для JS-сайтов)
    """
    if 'url' not in values or not values['url']:
        return False

    # Если RSS-лента предоставила полный текст — используем его без запроса URL
    if values.get('full_text_rss'):
        txt = html_module.unescape(values['full_text_rss'])
        txt = re.sub(r'<[^>]+>', ' ', txt)
        txt = re.sub(r'\s+', ' ', txt).strip()
        if len(txt) > 100:
            values['meta_img'] = ''
            txt = cloud.make_description(txt)
            values['file'] = len(txt)
            lang = values.get('lang', '') or init_lang
            error, values['text_ru'], values['text_en'], values['text_he'] = make_translate(txt, lang)
            values['error_translator'] = values.get('error_translator', False) or error
            return True

    url = values['url']
    _domain_throttle(url)
    meta_img = None
    txt = None

    # Попытка 1: newspaper3k (быстрый парсер)
    try:
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
        # FIX: newspaper при 403 не бросает exception, а ставит download_exception_msg.
        # Раньше код шёл дальше с пустым текстом — теперь проверяем явно.
        if not article.download_exception_msg:
            article.parse()
            if article.text and len(article.text) > 100 and not _is_challenge_page(article.text):
                meta_img = article.meta_img
                txt = article.text
    except Exception:
        pass

    # Попытка 2: hill_article (httpx HTTP/2 + AMP-варианты + curl_cffi — обход 403)
    if not txt:
        try:
            import hill_article  # ленивый импорт: trafilatura + readability загружаются только здесь
            meta_img, txt = hill_article.main(url)
            if txt and _is_challenge_page(txt):
                meta_img, txt = None, None
        except Exception:
            pass

    # Попытка 3: grab_article (Playwright — рендерит JS, тяжёлый)
    if not txt:
        try:
            import grab_article  # ленивый импорт: playwright загружается только здесь
            meta_img, txt = _get_article_loop().run_until_complete(grab_article.main(url))
            if txt and _is_challenge_page(txt):
                meta_img, txt = None, None
        except Exception:
            pass

    # Fallback: если URL недоступен (DDoSGuard и аналоги), используем description из RSS.
    # Так article-текст не теряется полностью — доступен поиск тем и запись в облако.
    if not txt:
        desc = (values.get('description_ru') or values.get('description_en')
                or values.get('description_he'))
        if desc and len(desc) > 50:
            values['meta_img'] = ''
            values['file'] = 0
            values['text_ru'] = values.get('description_ru', '')
            values['text_en'] = values.get('description_en', '')
            values['text_he'] = values.get('description_he', '')
            return True
        return False

    time.sleep(delay)
    values['meta_img'] = meta_img or ''
    txt = cloud.make_description(txt)
    if not txt:
        # После очистки текст оказался пустым (весь контент — мусорные строки).
        # file=-1 сигнализирует об этом в БД; запись в облако не производится.
        values['file'] = -1
        return False
    values['file'] = len(txt)
    error, values['text_ru'], values['text_en'], values['text_he'] = make_translate(txt, init_lang)
    values['error_translator'] = values.get('error_translator', False) or error
    return True


def translate(txt, lang, max_retries=3, initial_delay=2):
    result = ''
    current_delay = initial_delay

    for attempt in range(max_retries):
        try:
            # Пробуем выполнить перевод
            result = GoogleTranslator(target=lang).translate(txt)
            return True, result if result is not None else txt
        except TooManyRequests:
            # Логирование ошибки
            print(
                f"Ошибка TooManyRequests при переводе на {lang}. Попытка {attempt + 1}/{max_retries}, ожидание {current_delay} сек.")

            if attempt < max_retries - 1:
                time.sleep(current_delay)
                current_delay *= 2  # Увеличиваем задержку экспоненциально
            else:
                # Последняя попытка не удалась
                print(f"Превышено максимальное количество попыток перевода. Язык: {lang}")
                return False, txt  # Возвращаем исходный текст и признак ошибки
        except Exception as e:
            print(f"Неожиданная ошибка при переводе на {lang}: {str(e)}. Попытка {attempt + 1}/{max_retries}")

            if attempt < max_retries - 1:
                time.sleep(current_delay)
                current_delay *= 2
            else:
                return False, txt

    # Этот код не должен выполниться, но на всякий случай
    return False, txt

# Пример использования
# text = "hello"
# translated_text = translate_text(text, 'ru')
# print(translated_text)
if __name__ == "__main__":
    values = {"url": "https://iz.ru/2054553/2026-03-06/tramp-potreboval-pomilovat-netaniakhu"}
    load_article(values)