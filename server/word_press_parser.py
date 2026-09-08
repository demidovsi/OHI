"""
Парсер новостей с WordPress-сайтов.

Собирает новости с пагинацией, заходя в каждую статью за полным текстом.
Определяет язык, извлекает заголовок, описание, автора, дату, теги.
Фильтрует карточки-ссылки на соцсети.

Зависимости: requests, beautifulsoup4, lxml, python-dateutil
"""
from __future__ import annotations

import re
import time
from typing import List, Dict, Optional, Set
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup, Tag
from dateutil.parser import isoparse

import trafaret_thread
import common
from common import SRC
import cloud
import translate

# ---------------- Social title filter ----------------
SOCIAL_TITLES: Set[str] = {
    # English
    "facebook", "x", "twitter", "telegram", "youtube", "instagram",
    "tiktok", "whatsapp", "linkedin", "pinterest", "reddit", "threads",
    "vk", "vkontakte",
    # Hebrew
    "פייסבוק", "טוויטר", "טלגרם", "יוטיוב", "אינסטגרם",
    "טיקטוק", "וואטסאפ", "ווטסאפ", "לינקדאין", "פינטרסט", "רדיט",
}

def is_social_title(title: Optional[str]) -> bool:
    if not title:
        return False
    t = re.sub(r"\s+", " ", title).strip().lower()
    return t in SOCIAL_TITLES

# ---------------- HTTP ----------------
def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                       "KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "he,ru;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })
    return s

def get_soup(session: requests.Session, url: str, timeout: int = 25) -> BeautifulSoup:
    r = session.get(url, timeout=timeout)
    r.raise_for_status()

    ctype = r.headers.get("Content-Type", "").lower()
    txt = r.text

    # если это RSS/Atom/XML — используем XML-парсер (lxml-xml), иначе HTML (lxml)
    if "xml" in ctype or txt.lstrip().startswith("<?xml"):
        parser = "lxml-xml"   # можно "xml", но "lxml-xml" быстрее/строже
    else:
        parser = "lxml"

    return BeautifulSoup(txt, features=parser)

# ---------------- Utils ----------------
def clean_text(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()

def abs_url(base: str, href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    return urljoin(base, href)

def url_to_slug(u: Optional[str]) -> Optional[str]:
    if not u:
        return None
    path = urlparse(u).path.rstrip("/")
    if not path:
        return None
    return path.split("/")[-1]

# ---------------- Language detection ----------------
def html_declared_lang(soup: BeautifulSoup) -> Optional[str]:
    """
    Возвращает язык из <html lang="..."> как двухбуквенный код (he/ru/en/...), если есть.
    """
    html = soup.find("html")
    if not html:
        return None
    val = (html.get("lang") or "").strip().lower().replace("_", "-")
    if not val:
        return None
    if val.startswith("iw"):  # старый код иврита
        return "he"
    return val.split("-")[0]

_LANG_PATTERNS = {
    "he": re.compile(r"[\u0590-\u05FF]"),           # Hebrew
    "ar": re.compile(r"[\u0600-\u06FF]"),           # Arabic
    "ru": re.compile(r"[А-Яа-яЁё\u0400-\u04FF]"),   # Cyrillic (Russian)
    "en": re.compile(r"[A-Za-z]"),                  # Latin letters
}

def detect_language(text: str, hint: Optional[str] = None) -> str:
    """
    Примитивный определитель языка по подсчёту символов.
    Если есть hint (например, из <html lang>), он возвращается сразу.
    В противном случае выбирается язык с максимальным счётом.
    Если букв мало (шум), вернёт 'und'.
    """
    if hint in {"he", "ru", "en", "ar"}:
        return hint

    txt = text or ""
    counts = {k: len(p.findall(txt)) for k, p in _LANG_PATTERNS.items()}
    total_letters = sum(counts.values())
    if total_letters == 0:
        return "und"
    lang = max(counts, key=counts.get)
    # Требуем хотя бы 20% букв этого алфавита среди всех букв
    return lang if counts[lang] / total_letters >= 0.2 else "und"

# ---------------- Date helpers ----------------
_DATE_TEXT_PATTERNS = [
    r'(\d{1,2}[./]\d{1,2}[./]\d{2,4})(?:\s+(\d{1,2}:\d{2}))?',
]
_DATE_FMT = ["%d/%m/%Y %H:%M", "%d.%m.%Y %H:%M", "%d/%m/%Y", "%d.%m.%Y"]

def extract_iso_date_from_card(card: Tag) -> Optional[str]:
    t = card.select_one('time[datetime], .entry-date[datetime]')
    if t and t.get("datetime"):
        try:
            return isoparse(t["datetime"]).isoformat()
        except Exception:
            pass

    txt = card.get_text(" ", strip=True)
    for pat in _DATE_TEXT_PATTERNS:
        m = re.search(pat, txt)
        if not m:
            continue
        s = m.group(1) + (f" {m.group(2)}" if m.group(2) else "")
        for fmt in _DATE_FMT:
            try:
                return datetime.strptime(s, fmt).isoformat()
            except ValueError:
                continue
    return None

def extract_iso_date_from_article(soup: BeautifulSoup) -> Optional[str]:
    meta = soup.select_one('meta[property="article:published_time"], meta[name="article:published_time"]')
    if meta and meta.get("content"):
        try:
            return isoparse(meta["content"]).isoformat()
        except Exception:
            pass

    t = soup.select_one('time[datetime], .entry-date[datetime], time.published[datetime]')
    if t and t.get("datetime"):
        try:
            return isoparse(t["datetime"]).isoformat()
        except Exception:
            pass

    t2 = soup.select_one('[itemprop="datePublished"][datetime], [itemprop="datePublished"][content]')
    if t2:
        d = t2.get("datetime") or t2.get("content")
        if d:
            try:
                return isoparse(d).isoformat()
            except Exception:
                pass

    body_txt = soup.get_text(" ", strip=True)
    for pat in _DATE_TEXT_PATTERNS:
        m = re.search(pat, body_txt)
        if not m:
            continue
        s = m.group(1) + (f" {m.group(2)}" if m.group(2) else "")
        for fmt in _DATE_FMT:
            try:
                return datetime.strptime(s, fmt).isoformat()
            except ValueError:
                continue
    return None

# ---------------- Card finding ----------------
CARD_SELECTORS = [
    "article.post", "article.type-post",
    ".td-block-span6", ".td_module_1", ".td_module_10", ".td_module_11",
    ".jeg_post", ".jeg_posts", ".jeg_thumb",
    ".elementor-post", ".elementor-grid-item",
    ".post-item", ".post-card", ".loop-post", ".entry", ".entry-card",
    ".archive-post", ".archive-item", ".news-item", ".cat_list .item",
]

def find_cards(soup: BeautifulSoup) -> List[Tag]:
    cards: List[Tag] = []
    for sel in CARD_SELECTORS:
        cards.extend(soup.select(sel))
    seen = set()
    uniq = []
    for c in cards:
        if id(c) not in seen:
            uniq.append(c)
            seen.add(id(c))
    if not uniq:
        blocks = soup.select("main, .content, .container, #content, .site-content")
        if not blocks:
            blocks = [soup]
        for b in blocks:
            for li in b.select("li a[href]"):
                if li.find_parent("nav"):
                    continue
                uniq.append(li)
    return uniq

# ---------------- List-card fields ----------------
def extract_from_card(card: Tag, base_url: str, page_lang_hint: Optional[str]) -> Optional[Dict]:
    a = (card.select_one(".entry-title a, h2 a, h3 a, .jeg_post_title a, "
                         ".elementor-post__title a, .title a, a[href]") or card.find("a", href=True))
    url = abs_url(base_url, a["href"]) if a else None
    title_el = (card.select_one(".entry-title, .jeg_post_title, .elementor-post__title, h2, h3")
                or (a if a and a.get_text(strip=True) else None))
    title = clean_text(title_el.get_text(strip=True) if title_el else None)
    if not url or not title:
        return None

    # фильтр: отбрасываем карточки, где title == соцсеть
    if is_social_title(title):
        return None

    ex_el = card.select_one(".entry-summary, .td-excerpt, .jeg_post_excerpt, "
                            ".elementor-post__excerpt, .post-excerpt")
    if ex_el:
        excerpt = clean_text(ex_el.get_text(" ", strip=True))
    else:
        p_txt = ""
        for cand in card.select("p"):
            txt = clean_text(cand.get_text(" ", strip=True))
            if len(txt) >= 20:
                p_txt = txt
                break
        excerpt = p_txt

    img = card.select_one("img")
    image = None
    if img:
        image = img.get("data-src") or img.get("data-lazy-src") or img.get("src")
        if not image and img.get("srcset"):
            image = img.get("srcset").split(",")[0].strip().split(" ")[0]
        image = abs_url(base_url, image) if image else None

    date_iso = extract_iso_date_from_card(card)
    cat_el = card.select_one(".cat a, .meta-category a, .entry-category a, .jeg_cat a, .category a")
    category = clean_text(cat_el.get_text(strip=True)) if cat_el else None

    # Язык по заголовку/анонсу с учётом lang страницы
    lang_text = " ".join(filter(None, [title, excerpt]))
    language = detect_language(lang_text, hint=page_lang_hint)

    return {
        "title": title,
        "url": url,
        "slug": url_to_slug(url),
        "meta_img": image,
        "description": excerpt or "",
        "public_date": date_iso,
        "category": category,
        "source_url": base_url,
        "language": language,
    }

# ---------------- Article page scraping ----------------
REMOVE_SELECTORS = [
    "script", "style", "noscript", "iframe", "svg", "form",
    ".post-navigation", ".nav-links", ".pagination", ".wp-block-gallery",
    ".share", ".sharedaddy", ".social", ".td-post-source-tags", ".tags", ".tagcloud",
    ".advert", ".ads", ".ad", ".promo",
    "header", "footer", "aside"
]

CONTENT_CONTAINERS = [
    "article .entry-content", ".entry-content",
    ".td-post-content", ".td-post-text-content",
    ".post-content", ".single-content", ".post__content", ".post-body",
    ".content-inner", ".jeg_inner_content", ".jeg_post_content",
    ".elementor-widget-theme-post-content", ".elementor-post__content",
    ".theiaPostSlider_preloadedSlide",
    "article .content"
]

def extract_author(soup: BeautifulSoup) -> Optional[str]:
    a = (soup.select_one('meta[name="author"]') or
         soup.select_one(".author a, .byline a, .post-author a, .jeg_meta_author a, .td-post-author-name a"))
    if a:
        return clean_text(a["content"] if a.has_attr("content") else a.get_text(" ", strip=True))
    return None

def extract_tags(soup: BeautifulSoup) -> List[str]:
    tags = []
    for a in soup.select(".tags a, .tagcloud a, .post-tags a, .entry-tags a, .td-tags a, a[rel=tag]"):
        t = clean_text(a.get_text(" ", strip=True))
        if t and t not in tags:
            tags.append(t)
    return tags

def extract_content_text(soup: BeautifulSoup) -> str:
    container = None
    for sel in CONTENT_CONTAINERS:
        container = soup.select_one(sel)
        if container:
            break
    if not container:
        container = soup.select_one("article") or soup.select_one("main") or soup

    for sel in REMOVE_SELECTORS:
        for el in container.select(sel):
            el.decompose()

    for el in container.select(".wp-caption-text, figcaption, .credit, .photo-credit"):
        el.decompose()

    parts: List[str] = []
    for elem in container.descendants:
        if isinstance(elem, Tag) and elem.name in ("h1", "h2", "h3", "p", "li", "blockquote"):
            txt = clean_text(elem.get_text(" ", strip=True))
            if txt:
                parts.append(txt)
    text = "\n".join(parts).strip()

    if not text:
        text = clean_text(soup.get_text(" ", strip=True))
    return text

def get_article_details(session: requests.Session, url: str, lang_hint: Optional[str]) -> Dict[str, Optional[str]]:
    soup = get_soup(session, url)
    time.sleep(0.2)  # дружелюбие к анти-боту

    # Языковой hint можно уточнить по самой странице статьи
    page_lang_hint = html_declared_lang(soup) or lang_hint

    content = extract_content_text(soup)
    author = extract_author(soup)
    tags = extract_tags(soup)
    date_full = extract_iso_date_from_article(soup)
    language_article = detect_language(content or "", hint=page_lang_hint)

    return {
        "content": content,
        "author": author,
        "tags": tags,
        "date_full": date_full,
        "language": language_article,
    }

# ---------------- Pagination ----------------
NEXT_SELECTORS = [
    'link[rel="next"]',
    'a[rel="next"]',
    ".nav-links a.next", ".pagination a.next", ".page-numbers a.next", "a.next.page-numbers",
    ".nav-previous a[rel=next]", ".older a", "a.nextpostslink",
]

def find_next_url(soup: BeautifulSoup, current_url: str) -> Optional[str]:
    ln = soup.select_one('link[rel="next"]')
    if ln and ln.get("href"):
        return abs_url(current_url, ln["href"])
    for sel in NEXT_SELECTORS[1:]:
        a = soup.select_one(sel)
        if a and a.get("href"):
            return abs_url(current_url, a["href"])

    pagers = soup.select(".pagination, .nav-links, .page-numbers")
    for p in pagers:
        active = p.select_one(".current") or p.select_one(".active")
        if active:
            nxt = active.find_next("a")
            if nxt and nxt.get("href"):
                return abs_url(current_url, nxt["href"])

    for a in soup.select("a[href]"):
        text = (a.get_text(" ", strip=True) or "").lower()
        if any(t in text for t in ["next", "older", "הבא", "לעמוד הבא", "הבא »", "לעמוד הבא »"]):
            return abs_url(current_url, a["href"])
    return None

# ---------------- Main ----------------
def scrape_all_news(
    list_url: str,
    max_pages: Optional[int] = 1,
    delay_between_articles: float = 0.1,
    with_article: bool = True,
) -> List[Dict]:
    """
    Собирает карточки по всем страницам пагинации.
    Если with_article=True — заходит в каждую статью за полным текстом/автором/тегами/уточнённой датой (+ определяет язык по полному тексту).
    Если with_article=False — возвращает только данные из карточек (content="", author=None, tags=[]), язык по title/excerpt.
    Фильтрует карточки с title, равным названию соцсети (англ./иврит).
    """
    session = make_session()
    out: List[Dict] = []
    seen_urls = set()

    page_url = list_url
    visited_pages = set()
    pages_done = 0

    while page_url and page_url not in visited_pages:
        visited_pages.add(page_url)
        soup = get_soup(session, page_url)

        # Hint от списка (если указан <html lang>)
        page_lang_hint = html_declared_lang(soup)

        cards = find_cards(soup)
        for card in cards:
            item = extract_from_card(card, page_url, page_lang_hint)
            if not item:
                continue
            if item["url"] in seen_urls:
                continue

            if with_article:
                try:
                    details = get_article_details(session, item["url"], lang_hint=item.get("language"))
                except Exception:
                    details = {"content": "", "author": None, "tags": [], "date_full": None, "language": None}
                item["content"] = details["content"]
                item["author"] = details["author"]
                item["tags"] = details["tags"]
                if details["date_full"]:
                    item["public_date"] = details["date_full"]
                # Язык из статьи приоритетнее, если определился
                if details.get("language") and details["language"] != "und":
                    item["language"] = details["language"]
                if delay_between_articles:
                    time.sleep(delay_between_articles)
            else:
                item["content"] = ""
                item["author"] = None
                item["tags"] = []

            out.append(item)
            seen_urls.add(item["url"])

        pages_done += 1
        if max_pages and pages_done >= max_pages:
            break
        page_url = find_next_url(soup, page_url)
    return out


class WordPressParser(trafaret_thread.TrafaretThread):
    """
    Поток парсинга новостей с WordPress-сайтов.

    Использует scrape_all_news() для извлечения карточек новостей,
    проверяет на наличие поисковых образов, переводит и записывает в БД и облако.
    """
    # FIX: удалены rss = {}, rss_themes = list() (изменяемые class-level defaults)
    # FIX: удалён rss_id = 0 (устанавливается в __init__)

    def __init__(self, source, code_function, code_period, description, rss_id):
        self.print_load = False
        self.rss_id = rss_id
        # FIX: Изменяемый атрибут — на уровне экземпляра
        self.rss_themes = []
        super(WordPressParser, self).__init__(source, code_function, code_period, description)

    def initiation_parameters(self):
        """Задаёт параметры по умолчанию: период опроса (10 мин) и активность."""
        super(WordPressParser, self).initiation_parameters()
        self.par.append({"code": "period", "value": 10})
        self.par.append({"code": "active", "value": 1})

    def make_values_init(self, rss, item):
        """
        Предварительный (лёгкий) разбор: только ссылка и дата.
        Используется для быстрой проверки — существует ли новость уже в БД.
        """
        rss['count'] += 1
        values = dict()
        values["rss"] = rss['id']
        values['url'] = item['url']
        values['public_date'] = common.get_public_date(item['public_date'])
        return values

    def make_values(self, rss, item):
        """
        Полный разбор элемента: заголовок, описание, автор, дата, изображение.
        Переводит тексты на три языка (ru, en, he).
        """
        values = dict()
        values["rss"] = rss['id']
        values["lang"] = item['language']
        values["meta_img"] = item['meta_img']
        values['error_translator'] = False
        values["url"] = item['url']

        # Заголовок новости
        txt = item['title']
        err, values['title_ru'], values['title_en'], values['title_he'] = translate.make_translate(txt, values["lang"])

        # Текст/описание новости
        txt = item['description']
        if txt:
            error, values['description_ru'], values['description_en'], values['description_he'] = (
                translate.make_translate(txt, values["lang"]))
            values['error_translator'] = values['error_translator'] or error

        # Автор новости
        txt = item['author']
        if txt:
            values['author'] = txt  # FIX: было "{txt}".format(txt=txt) — избыточно

        # Дата публикации
        values['public_date'] = common.get_public_date(item['public_date'])

        # Дата и время записи новости в БД (UTC)
        # FIX: было datetime.utcnow() — deprecated в Python 3.12+
        values["at_date_time"] = datetime.now(timezone.utc).isoformat()
        return values

    def analyses_rss(self, rss):
        """
        Анализ одного WordPress-сайта:
        1. Скрейпинг карточек новостей (с заходом в каждую статью)
        2. Для каждой новости — проверка на дубликат, поиск поисковых образов
        3. При совпадении — перевод, запись в БД и облако, уведомление в Telegram
        """
        t0 = time.time()
        url = rss['url']  # FIX: переменная url не была определена — NameError в except-блоке

        rss['count'] = 0
        rss['count_new'] = 0
        items = []
        try:
            items = scrape_all_news(url, max_pages=1, with_article=True)
        except Exception as e:
            common.write_log_db(
                '⚠️ warning', SRC,
                f"❗Не прочитаны статьи из {url}\n{e}",
                law_id=rss['sh_name'] + ' - ' + self.source, page=rss['id'])

        self.global_count = len(items)

        for j, item in enumerate(items):
            try:
                self.number = j + 1
                # Предварительный разбор — проверка на дубликат
                values = self.make_values_init(rss, item)
                exist = common.is_exist_object(values, self.token)
                if exist is not None and not exist:
                    # Новость ещё не в БД — полный разбор с переводом
                    values = self.make_values(rss, item)
                    common.seek(self.rss_themes, values)  # поиск поисковых образов

                    # Текст статьи (уже получен scrape_all_news с with_article=True)
                    txt = item['content']
                    values['file'] = len(txt)
                    if txt:
                        error, values['text_ru'], values['text_en'], values['text_he'] = translate.make_translate(txt, values['lang'])
                        values['error_translator'] = values['error_translator'] or error
                    else:
                        common.write_log_db(
                            '❗Не прочитан текст', SRC,
                            f"❗Не прочитан текст статьи по ссылке {values['url']}\nНомер {j + 1} из {len(items)}; ",
                            law_id=rss['sh_name'] + ' - ' + self.source, page=rss['id'])

                    # Если образы не найдены в заголовке/описании — ищем в тексте статьи
                    if len(values['themes']) == 0 and txt:
                        common.seek_article(self.rss_themes, values)
                    if values['themes']:  # есть совпадения с поисковыми образами
                        ok_write = common.write_history(values, self.token, rss, self.source)
                        if ok_write:
                            # Формирование строки тем для Telegram
                            themes = ''
                            for theme in values['themes']:
                                themes = themes + ', ' if themes else themes
                                themes += common.get_name_theme(self.rss_themes, theme)
                            common.make_tg(self.source, themes, values, rss, j, self.global_count)
                            # Запись связей тема <-> новость
                            for theme in values['themes']:
                                common.make_theme(theme, values, self.source, self.token)
                            # Сохранение переведённых текстов в облако
                            if txt:
                                cloud.save_file_bucket('en_' + str(values['id']), values['text_en'])
                                cloud.save_file_bucket('ru_' + str(values['id']), values['text_ru'])
                                cloud.save_file_bucket('he_' + str(values['id']), values['text_he'])
                # Помечаем новость как обработанную (в т.ч. если уже существовала)
                exists = common.is_exist_object(values, self.token)
                if exists is not None and not exists:
                    common.fix_new(values, self.token)
            except Exception as er:
                common.write_log_db(
                    '❌error', SRC,
                    f'j={j + 1} из {len(items)}'
                    f"\nОшибка {er}\nОбработка новости с сайта\n\n{url}\nanalyses_rss",
                    law_id=rss['sh_name'] + ' - ' + self.source, td=time.time() - t0)
            time.sleep(0.5)
        del items  # scraped-статьи с полными текстами больше не нужны — освобождаем память
        st_new = '➕ ' if rss['count_new'] else ''
        self.finish_text += (
            f'Закончена обработка новостной ленты сайта "{rss["sh_name"]}" (ID={rss["id"]}); '
            f'новостей={self.global_count};\n{st_new}записано={rss["count_new"]}; обработано={rss["count"]}'
        )
        return True

    def work(self):
        """
        Основной рабочий метод потока.
        Загружает параметры RSS, авторизуется и запускает анализ WordPress-сайта.
        """
        super(WordPressParser, self).work()
        if common.get_value_config_param('active', self.par) != 1:
            return False
        result, self.rss = common.load_rss(self.rss_id, self.source)
        self.law_id = self.rss['sh_name']
        if result:
            result, self.rss_themes = common.load_list_themes(self.source)
            if result:
                result = self.make_login()
                # FIX: .get('stop') вместо ['stop'] — защита от KeyError
                if result and self.rss.get('stop') != True:
                    common.write_log_db('✈️Start', SRC,
                                        f"Начало работы по опросу ленты новостей с сайта [{self.rss['sh_name']}] ID={self.rss['id']}",
                                        page=self.rss['id'], law_id=self.rss['sh_name'] + ' - ' + self.source)
                    if len(self.rss_themes) == 0:
                        self.finish_text = "Отсутствуют поисковые образы для сайтов с RSS"
                    else:
                        self.analyses_rss(self.rss)
                        return True  # повторить через заданный период даже если ошибка внутри анализа
                else:
                    return False  # повторить через 10 минут
        return result


# ---------------- CLI demo ----------------
# if __name__ == "__main__":
#     import json  # нужен только для demo
#     t0 = time.time()
#     url = "https://haifakrayot.co.il/חדשות/חדשות-חיפה"
#     items = scrape_all_news(url, max_pages=1, with_article=True)
#     print(json.dumps(items, ensure_ascii=False, indent=2))
#     print(len(items), "items", f"{time.time() - t0:.1f} sec")

if __name__ == "__main__":
    WordPressParser('SearchRSS', 'SearchRSS', 'period', 'Поток "Поиск тем в новостных лентах"', 17).start()
    while True:
        time.sleep(5)
