#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
grab_article.py — извлечение текста статей с новостных сайтов (ynet и др.)
Теперь включает:
  • articleBody из JSON-LD (application/ld+json)
  • meta_img (главное изображение) из JSON-LD и <meta> (og:image / twitter:image)

Примеры:
  python grab_article.py https://www.ynet.co.il/news/article/bjtrqnkfle#google_vignette
  python grab_article.py --file feeds.txt --out out_dir
"""

import argparse
import asyncio
import os
import re
import sys
import textwrap
import threading
import json
from dataclasses import dataclass
from typing import List, Optional, Tuple, Iterable, Union
from urllib.parse import urljoin

import trafilatura
from trafilatura.settings import use_config

from readability import Document
from bs4 import BeautifulSoup

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

try:
    from playwright_stealth import stealth_async as _stealth_async
    _stealth_available = True
except Exception:
    _stealth_available = False


# --- Trafilatura конфиг
TRA_CONFIG = use_config()
TRA_CONFIG.set("DEFAULT", "EXTRACTION_TIMEOUT", "0")
TRA_CONFIG.set("DEFAULT", "MIN_OUTPUT_SIZE", "200")
TRA_CONFIG.set("DEFAULT", "NO_FOLLOW", "true")
TRA_CONFIG.set("DEFAULT", "STRICT", "false")


@dataclass
class GrabResult:
    url: str
    title: Optional[str]
    text: Optional[str]
    source: str  # 'jsonld', 'trafilatura', 'playwright+jsonld', 'playwright+trafilatura', 'readability', 'combo'
    error: Optional[str] = None
    image_url: Optional[str] = None  # <-- meta_img


def norm_url(url: str) -> str:
    return url.split("#", 1)[0].strip()


def clean_text(s: Optional[str]) -> Optional[str]:
    if not s:
        return s
    s = re.sub(r'\r\n?', '\n', s)
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r'\n{3,}', '\n\n', s).strip()
    return s


def split_paragraphs(txt: str) -> List[str]:
    return [p.strip() for p in re.split(r'\n{2,}', txt) if p.strip()]


def combine_texts(primary: Optional[str], extra: Optional[str]) -> Optional[str]:
    """Объединяет тексты без дубликатов абзацев, сохраняя порядок."""
    if not primary and not extra:
        return None
    if primary and not extra:
        return clean_text(primary)
    if extra and not primary:
        return clean_text(extra)
    p_main = split_paragraphs(primary or "")
    p_extra = split_paragraphs(extra or "")
    seen = set()
    out: List[str] = []
    for p in p_main + p_extra:
        key = re.sub(r'\s+', ' ', p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return clean_text("\n\n".join(out))


def trafilatura_extract(html: str, url: str) -> Tuple[Optional[str], Optional[str]]:
    if not html:
        return None, None
    try:
        txt = trafilatura.extract(
            html, url=url, config=TRA_CONFIG,
            include_comments=False, include_tables=False,
            favor_recall=True, output='txt'
        )
        data = trafilatura.bare_extraction(html, url=url, config=TRA_CONFIG) or {}
        title = data.get('title')
        return clean_text(title), clean_text(txt)
    except Exception:
        return None, None


def readability_extract(html: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        doc = Document(html)
        title = clean_text(doc.short_title())
        summary_html = doc.summary()
        soup = BeautifulSoup(summary_html, "lxml")
        blocks = []
        for tag in soup.find_all(["h1", "h2", "h3", "p", "li"]):
            t = tag.get_text(" ", strip=True)
            if t and len(t) > 1:
                blocks.append(t)
        text = clean_text("\n".join(blocks)) if blocks else None
        return title, text
    except Exception:
        return None, None


# ----------------- JSON-LD (articleBody / image) -----------------

ARTICLE_TYPES = {
    "Article", "NewsArticle", "Report", "BlogPosting", "AnalysisNewsArticle",
    "OpinionNewsArticle", "BackgroundNewsArticle", "ReportageNewsArticle"
}

def _iter_json_nodes(obj: Union[dict, list]) -> Iterable[dict]:
    """Итерирует по всем словарям во вложенных структурах JSON."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            if isinstance(v, (dict, list)):
                yield from _iter_json_nodes(v)
    elif isinstance(obj, list):
        for it in obj:
            if isinstance(it, (dict, list)):
                yield from _iter_json_nodes(it)

def _load_json_safely(s: str) -> Optional[Union[dict, list]]:
    try:
        return json.loads(s)
    except Exception:
        return None

def _text_from_html(src: str) -> str:
    soup = BeautifulSoup(src, "lxml")
    return soup.get_text(" ", strip=True)

def _normalize_url(u: Optional[str], base: str) -> Optional[str]:
    if not u:
        return None
    return urljoin(base, u)

def jsonld_article_extract(html: str, soup=None) -> Tuple[Optional[str], Optional[str]]:
    """Достаёт articleBody/headline из JSON-LD (application/ld+json)."""
    if soup is None:
        soup = BeautifulSoup(html, "lxml")
    scripts = soup.find_all("script", attrs={"type": ["application/ld+json", "application/json"]})
    best_title = None
    bodies: List[str] = []
    for s in scripts:
        raw = s.string or s.get_text()
        if not raw or len(raw) < 10:
            continue
        data = _load_json_safely(raw)
        if data is None:
            continue
        for node in _iter_json_nodes(data):
            t = node.get("@type")
            types = set([t]) if isinstance(t, str) else set(t or [])
            if not types or ARTICLE_TYPES.isdisjoint(types):
                continue
            body = node.get("articleBody") or node.get("articlebody")
            if isinstance(body, str) and len(body.strip()) > 20:
                text = _text_from_html(body)
                if text and len(text) > 20:
                    bodies.append(text)
            if not best_title:
                ttl = node.get("headline") or node.get("name") or node.get("alternativeHeadline")
                if isinstance(ttl, str) and len(ttl.strip()) > 3:
                    best_title = ttl.strip()
    if bodies:
        full = clean_text("\n\n".join(bodies))
        return clean_text(best_title), full
    return None, None

def jsonld_article_image(html: str, base_url: str, soup=None) -> Optional[str]:
    """Достаёт image/thumbnailUrl из JSON-LD (Article/NewsArticle)."""
    if soup is None:
        soup = BeautifulSoup(html, "lxml")
    scripts = soup.find_all("script", attrs={"type": ["application/ld+json", "application/json"]})
    def pick_from_image(img) -> Optional[str]:
        if isinstance(img, str):
            return img
        if isinstance(img, dict):
            return img.get("url") or img.get("contentUrl") or img.get("@id")
        if isinstance(img, list) and img:
            # возьмём первый валидный
            for it in img:
                got = pick_from_image(it)
                if got:
                    return got
        return None

    for s in scripts:
        raw = s.string or s.get_text()
        if not raw or len(raw) < 10:
            continue
        data = _load_json_safely(raw)
        if data is None:
            continue
        for node in _iter_json_nodes(data):
            t = node.get("@type")
            types = set([t]) if isinstance(t, str) else set(t or [])
            if not types or ARTICLE_TYPES.isdisjoint(types):
                continue
            img = pick_from_image(node.get("image")) or node.get("thumbnailUrl")
            if img:
                return _normalize_url(img, base_url)
    return None


# ----------------- META (og:image / twitter:image / link[rel=image_src]) -----------------

META_IMG_KEYS = {
    "og:image", "og:image:url", "og:image:secure_url",
    "twitter:image", "twitter:image:src",
    "parsely-image-url",  # встречается на некоторых сайтах
}

def extract_meta_image(html: str, base_url: str, soup=None) -> Optional[str]:
    if soup is None:
        soup = BeautifulSoup(html, "lxml")
    candidates: List[str] = []

    # <meta ...>
    for m in soup.find_all("meta"):
        prop = (m.get("property") or m.get("name") or m.get("itemprop") or "").strip().lower()
        if prop in META_IMG_KEYS or prop == "image":
            content = m.get("content") or m.get("value")
            if content and len(content) > 5:
                candidates.append(content.strip())

    # <link rel="image_src" href="...">
    for l in soup.find_all("link", rel=True, href=True):
        relval = " ".join(l.get("rel") if isinstance(l.get("rel"), list) else [l.get("rel")]).lower()
        if "image_src" in relval or "thumbnail" in relval:
            candidates.append(l.get("href").strip())

    # Уберём пустые/повторы и вернём первый нормализованный
    seen = set()
    for c in candidates:
        u = _normalize_url(c, base_url)
        if not u:
            continue
        if u not in seen:
            seen.add(u)
            return u
    return None


# ----------------- Playwright (рендер) -----------------

_playwright_semaphore = threading.Semaphore(3)


async def render_and_get_html(url: str, timeout_ms: int = 30000) -> str:
    _playwright_semaphore.acquire()
    try:
        _launch_args = ['--disable-blink-features=AutomationControlled']
        if sys.platform.startswith('linux'):
            _launch_args += ['--no-sandbox', '--disable-setuid-sandbox']
        async with async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(
                    headless=True,
                    args=_launch_args
                )
            except Exception as _launch_err:
                if "Executable doesn" in str(_launch_err):
                    # Браузер не установлен — скачаем и повторим запуск
                    import subprocess
                    subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'])
                    browser = await pw.chromium.launch(
                        headless=True,
                        args=_launch_args
                    )
                else:
                    raise
            try:
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/123.0.0.0 Safari/537.36"
                    ),
                    locale="he-IL",
                    bypass_csp=True
                )
                # Скрываем navigator.webdriver — DDoSGuard проверяет этот флаг
                await context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )

                block_patterns = [
                    "doubleclick.net", "googlesyndication.com", "adservice.google.com",
                    "googletagmanager.com", "google-analytics.com",
                    "scorecardresearch.com", "facebook.net", "twitter.com/i",
                    "cdn.ampproject.org"
                ]

                async def route_intercept(route, request):
                    if request.resource_type in {"image", "media", "font", "stylesheet"}:
                        return await route.abort()
                    if any(domain in request.url for domain in block_patterns):
                        return await route.abort()
                    return await route.continue_()

                await context.route("**/*", route_intercept)
                page = await context.new_page()
                # playwright-stealth: полная маскировка (plugins, WebGL, chrome object, etc.)
                if _stealth_available:
                    await _stealth_async(page)

                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    if "google_vignette" in page.url:
                        base = url.split("#", 1)[0]
                        await page.goto(base, wait_until="domcontentloaded", timeout=timeout_ms)
                except PWTimeout:
                    await context.close()
                    return ""

                # Ждём завершения DDoSGuard JS-challenge (обычно ~5 сек).
                # Опрашиваем каждую секунду — выходим, когда challenge-маркеры исчезнут.
                _challenge_marks = ('ddos-guard', 'ожидайте', 'checking your browser')
                for _ in range(15):
                    await asyncio.sleep(1)
                    try:
                        body = await page.evaluate("document.body?.innerText || ''")
                        if not any(m in body.lower() for m in _challenge_marks):
                            break  # challenge пройден
                    except Exception:
                        break  # навигация в процессе

                # После challenge DDoSGuard перенаправляет на статью.
                # Ждём полной загрузки ('load') — это позволяет React/Vue
                # смонтировать компоненты и загрузить контент статьи через AJAX.
                try:
                    await page.wait_for_load_state('load', timeout=12000)
                except Exception:
                    try:
                        await page.wait_for_load_state('domcontentloaded', timeout=5000)
                    except Exception:
                        pass
                # Дополнительная пауза для SPA (React/Vue): даём JS-фреймворку
                # время отрисовать текст статьи после монтирования компонентов.
                await asyncio.sleep(2)

                hide_overlays_js = """
            (() => {
              const killSelectors = [
                '#google_vignette',
                'iframe[src*="doubleclick"]',
                'iframe[src*="googlesyndication"]',
                '[id^="google_ads"]',
                '.ad', '.ads', '[aria-label="Advertisement"]',
                'div[style*="z-index"][style*="position: fixed"]'
              ];
              for (const sel of killSelectors) {
                document.querySelectorAll(sel).forEach(el => el.remove());
              }
              const css = document.createElement('style');
              css.textContent = `* { pointer-events: auto !important; }`;
              document.head.appendChild(css);
            })();
            """
                try:
                    await page.evaluate(hide_overlays_js)
                except Exception:
                    pass

                try:
                    html = await page.content()
                except Exception:
                    html = ""

                await context.close()
                return html
            finally:
                await browser.close()
    finally:
        _playwright_semaphore.release()


# ----------------- Основной пайплайн -----------------

async def grab_one(url: str, min_chars: int = 400) -> GrabResult:
    url = norm_url(url)

    meta_img: Optional[str] = None

    # 1) без рендера — сначала JSON-LD (articleBody + image), затем Trafilatura
    downloaded = trafilatura.fetch_url(url)
    json_title, json_text = (None, None)
    if downloaded:
        # Парсим HTML один раз и передаём soup во все функции — иначе BeautifulSoup
        # создаёт дерево разбора на каждый вызов (3× для одного и того же HTML).
        _soup_dl = BeautifulSoup(downloaded, "lxml")
        meta_img = jsonld_article_image(downloaded, url, soup=_soup_dl) or extract_meta_image(downloaded, url, soup=_soup_dl)
        jt, jx = jsonld_article_extract(downloaded, soup=_soup_dl)
        del _soup_dl  # дерево разбора больше не нужно — освобождаем память
        json_title, json_text = jt, jx
        if jx and len(jx) >= min_chars:
            return GrabResult(url, json_title, jx, source="jsonld", image_url=meta_img)

    if downloaded:
        t_title, t_text = trafilatura_extract(downloaded, url)
        combo = combine_texts(t_text, json_text)
        title_final = t_title or json_title
        if combo and len(combo) >= min_chars:
            src = "combo" if json_text else "trafilatura"
            return GrabResult(url, title_final, combo, source=src, image_url=meta_img)

    # downloaded больше не нужен — освобождаем HTML (~100–500 КБ) до запуска Playwright
    del downloaded

    # 2) с рендером — снова JSON-LD/og:image, затем Trafilatura
    rendered_html = await render_and_get_html(url)
    if rendered_html:
        # Парсим rendered_html один раз для всех BS4-функций в этом блоке
        _soup_ren = BeautifulSoup(rendered_html, "lxml")
        if not meta_img:
            meta_img = jsonld_article_image(rendered_html, url, soup=_soup_ren) or extract_meta_image(rendered_html, url, soup=_soup_ren)
        jt2, jx2 = jsonld_article_extract(rendered_html, soup=_soup_ren)
        del _soup_ren  # дерево разбора больше не нужно — освобождаем память
        t2_title, t2_text = trafilatura_extract(rendered_html, url)
        combo2 = combine_texts(t2_text, jx2) or jx2
        title2 = t2_title or jt2

        if jx2 and len(jx2) >= min_chars:
            return GrabResult(url, jt2, jx2, source="playwright+jsonld", image_url=meta_img)

        if combo2 and len(combo2) >= min_chars:
            src = "combo" if jx2 else "playwright+trafilatura"
            return GrabResult(url, title2, combo2, source=src, image_url=meta_img)

    # 3) крайний случай — Readability (использует Document(html) + BS4 от summary, не от raw HTML)
    if rendered_html:
        r_title, r_text = readability_extract(rendered_html)
        del rendered_html  # HTML больше не нужен — освобождаем память до return
        combo3 = combine_texts(r_text, json_text)
        title3 = r_title or json_title
        if combo3 and len(combo3) >= min_chars // 2:
            return GrabResult(url, title3, combo3, source="readability", image_url=meta_img)

    return GrabResult(url, None, None, source="none", error="Не удалось извлечь содержимое", image_url=meta_img)


def save_text(out_dir: str, url: str, title: Optional[str], text: Optional[str]) -> str:
    os.makedirs(out_dir, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", url).strip("-")
    if len(slug) > 140:
        slug = slug[:140]
    path = os.path.join(out_dir, f"{slug}.txt")
    with open(path, "w", encoding="utf-8") as f:
        if title:
            f.write(title.strip() + "\n\n")
        if text:
            f.write(text.strip() + "\n")
    return path


def print_result(res: GrabResult, wrap: int = 100) -> None:
    pass
    # header = f"[{res.source}] {res.url}"
    # print("=" * len(header))
    # print(header)
    # print("=" * len(header))
    # if res.title:
    #     print(f"\nTITLE: {res.title}\n")
    # if res.image_url:
    #     print(f"IMAGE: {res.image_url}\n")
    # if res.text:
    #     print(textwrap.fill(res.text, width=wrap, replace_whitespace=False))
    # if res.error:
    #     print(f"\nERROR: {res.error}")
    # print("\n")


async def main(url):
    results = []
    try:
        res = await grab_one(url, min_chars=100)
    except Exception as e:
        res = GrabResult(url=url, title=None, text=None, source="exception", error=str(e))
    results.append(res)
    # print_result(results[0], wrap=100)
    return results[0].image_url, results[0].text


if __name__ == "__main__":
    try:
        asyncio.run(main('https://www.7kanal.co.il/news/272637'))
    except KeyboardInterrupt:
        pass
