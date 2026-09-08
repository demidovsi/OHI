#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
article_one.py — извлечение meta_img и текста статьи для ОДНОГО URL с защитами от 403.
Порядок:
  1) загрузка HTML:
     - httpx (HTTP/2, «браузерные» заголовки)
     - при 403/5xx: пробуем AMP-варианты (/amp/, ?outputType=amp)
     - curl_cffi (если установлен) с impersonate=chrome120
     - trafilatura.fetch_url — бэкап
  2) парсинг:
     - JSON-LD NewsArticle.articleBody (+ headline + image)
     - Trafilatura (fallback)
     - Readability (fallback)
Зависимости: httpx, bs4, lxml, trafilatura, readability-lxml
Опционально: curl_cffi

Пример:
  python article_one.py "https://thehill.com/opinion/international/5220181-trump-implications-foreign-policy/" --json
  python article_one.py "https://thehill.com/policy/energy-environment/5468696-fema-letter-trump-administration-disaster-response/" --verbose
  python article_one.py URL --proxy http://user:pass@host:port
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from html import unescape
from typing import Iterable, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from readability import Document
import trafilatura
from trafilatura.settings import use_config

# ---------- optional clients ----------
try:
    import httpx
except Exception:
    httpx = None

try:
    from curl_cffi import requests as curl_requests
except Exception:
    curl_requests = None


# ---------- Trafilatura конфиг ----------
TRA_CONFIG = use_config()
TRA_CONFIG.set("DEFAULT", "EXTRACTION_TIMEOUT", "0")
TRA_CONFIG.set("DEFAULT", "MIN_OUTPUT_SIZE", "200")
TRA_CONFIG.set("DEFAULT", "NO_FOLLOW", "true")
TRA_CONFIG.set("DEFAULT", "STRICT", "false")


ARTICLE_TYPES = {
    "Article", "NewsArticle", "Report", "BlogPosting",
    "AnalysisNewsArticle", "OpinionNewsArticle",
    "BackgroundNewsArticle", "ReportageNewsArticle",
}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

BROWSER_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,he;q=0.8,ru;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
}

@dataclass
class Grab:
    url: str
    title: Optional[str]
    text: Optional[str]
    image_url: Optional[str]
    source: str           # 'jsonld', 'combo', 'trafilatura', 'readability', 'none'
    error: Optional[str] = None


# ---------- утилиты ----------

def _clean_text(s: Optional[str]) -> Optional[str]:
    if not s:
        return s
    s = unescape(s).replace("\u00a0", " ")
    s = re.sub(r"\r\n?", "\n", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _iter_nodes(obj: Union[dict, list]) -> Iterable[dict]:
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            if isinstance(v, (dict, list)):
                yield from _iter_nodes(v)
    elif isinstance(obj, list):
        for it in obj:
            if isinstance(it, (dict, list)):
                yield from _iter_nodes(it)


def _pick_img(img):
    if isinstance(img, str):
        return img
    if isinstance(img, dict):
        return img.get("url") or img.get("contentUrl") or img.get("@id")
    if isinstance(img, list):
        for it in img:
            got = _pick_img(it)
            if got:
                return got
    return None


def _split_pars(txt: str) -> List[str]:
    return [p.strip() for p in re.split(r"\n{2,}", txt) if p.strip()]


def _combine(primary: Optional[str], extra: Optional[str]) -> Optional[str]:
    """Объединяет тексты без дубликатов абзацев, сохраняя порядок."""
    if not primary and not extra:
        return None
    if primary and not extra:
        return _clean_text(primary)
    if extra and not primary:
        return _clean_text(extra)
    p_main = _split_pars(primary or "")
    p_extra = _split_pars(extra or "")
    seen, out = set(), []
    for p in p_main + p_extra:
        key = re.sub(r"\s+", " ", p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return _clean_text("\n\n".join(out))


def _amp_variants(url: str) -> List[str]:
    u = url.split("#", 1)[0]
    out = [u]
    if not u.endswith("/"):
        out.append(u + "/")
    # типичные AMP варианты для WP/TheHill
    out.append(u.rstrip("/") + "/amp/")
    out.append(u + ("&" if "?" in u else "?") + "outputType=amp")
    # убираем дубликаты, сохраняем порядок
    seen, uniq = set(), []
    for v in out:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


# ---------- загрузка HTML с обходами ----------

def _try_httpx(url: str, headers: dict, proxy: Optional[str], timeout: int, verbose: bool):
    if httpx is None:
        return None, "httpx not installed"
    proxies = None
    if proxy:
        proxies = {"http://": proxy, "https://": proxy}
    try:
        with httpx.Client(http2=True, headers=headers, follow_redirects=True,
                          proxies=proxies, timeout=timeout) as client:
            r = client.get(url)
            if verbose:
                print(f"[httpx] {url} -> {r.status_code} len={len(r.text or '')}")
            if r.status_code == 200 and r.text and len(r.text) > 500:
                return r.text, None
            return None, f"HTTP {r.status_code}"
    except Exception as e:
        if verbose:
            print(f"[httpx] error: {e}")
        return None, f"httpx error: {e}"


def _try_curl_cffi(url: str, headers: dict, proxy: Optional[str], timeout: int, verbose: bool):
    if curl_requests is None:
        return None, "curl_cffi not installed"
    try:
        kwargs = dict(headers=headers, timeout=timeout, impersonate="chrome120", verify=True)
        if proxy:
            kwargs["proxies"] = {"http": proxy, "https": proxy}
        r = curl_requests.get(url, **kwargs)
        if verbose:
            print(f"[curl_cffi] {url} -> {r.status_code} len={len(r.text or '')}")
        if r.status_code == 200 and r.text and len(r.text) > 500:
            return r.text, None
        return None, f"HTTP {r.status_code}"
    except Exception as e:
        if verbose:
            print(f"[curl_cffi] error: {e}")
        return None, f"curl_cffi error: {e}"


def _try_requests(url: str, headers: dict, proxy: Optional[str], timeout: int, verbose: bool):
    try:
        with requests.Session() as s:
            s.headers.update(headers)
            if proxy:
                s.proxies.update({"http": proxy, "https": proxy})
            # иногда реферер помогает
            parsed = urlparse(url)
            s.headers.setdefault("Referer", f"{parsed.scheme}://{parsed.hostname}/")
            r = s.get(url, timeout=timeout, allow_redirects=True)
            if verbose:
                print(f"[requests] {url} -> {r.status_code} len={len(r.text or '')}")
            if r.status_code == 200 and r.text and len(r.text) > 500:
                return r.text, None
            return None, f"HTTP {r.status_code}"
    except Exception as e:
        if verbose:
            print(f"[requests] error: {e}")
        return None, f"requests error: {e}"


def fetch_html_smart(url: str, timeout: int = 25, proxy: Optional[str] = None, verbose: bool = False) -> Tuple[Optional[str], Optional[str], str]:
    """
    Возвращает (html, err, final_url_used).
    Стратегия: httpx -> (403/5xx) AMP-варианты -> curl_cffi -> requests -> trafilatura.fetch_url
    """
    candidates = _amp_variants(url)
    errors = []

    # 1) httpx (HTTP/2)
    if httpx is not None:
        for u in candidates:
            html, err = _try_httpx(u, dict(BROWSER_HEADERS), proxy, timeout, verbose)
            if html:
                return html, None, u
            errors.append(f"httpx:{u}:{err}")

    # 2) curl_cffi (имитация Chrome TLS)
    if curl_requests is not None:
        for u in candidates:
            html, err = _try_curl_cffi(u, dict(BROWSER_HEADERS), proxy, timeout, verbose)
            if html:
                return html, None, u
            errors.append(f"curl_cffi:{u}:{err}")

    # 3) requests (на всякий случай)
    for u in candidates:
        html, err = _try_requests(u, dict(BROWSER_HEADERS), proxy, timeout, verbose)
        if html:
            return html, None, u
        errors.append(f"requests:{u}:{err}")

    # 4) trafilatura.fetch_url как бэкап (учтите: без вашего прокси)
    try:
        for u in candidates:
            html = trafilatura.fetch_url(u)
            if verbose:
                print(f"[trafilatura.fetch_url] {u} -> {'ok' if html else 'None'}")
            if html:
                return html, None, u
    except Exception as e:
        errors.append(f"trafilatura:{e}")

    return None, "; ".join(errors[-5:]), url


# ---------- парсеры ----------

def extract_jsonld_article(html: str, base_url: str, soup=None) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """title, articleBody, image_url из JSON-LD NewsArticle"""
    if soup is None:
        soup = BeautifulSoup(html, "lxml")
    best_title, bodies, best_img = None, [], None

    for tag in soup.find_all("script", attrs={"type": ["application/ld+json", "application/json"]}):
        raw = tag.string or tag.get_text()
        if not raw or len(raw) < 10:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue

        for node in _iter_nodes(data):
            t = node.get("@type")
            types = set([t]) if isinstance(t, str) else set(t or [])
            if not types or ARTICLE_TYPES.isdisjoint(types):
                continue

            if not best_title:
                ttl = node.get("headline") or node.get("name") or node.get("alternativeHeadline")
                if isinstance(ttl, str) and ttl.strip():
                    best_title = ttl.strip()

            body = node.get("articleBody") or node.get("articlebody")
            if isinstance(body, str) and len(body.strip()) > 20:
                bodies.append(BeautifulSoup(unescape(body), "lxml").get_text(" ", strip=True))

            if not best_img:
                img = _pick_img(node.get("image")) or node.get("thumbnailUrl")
                if img:
                    best_img = urljoin(base_url, img)

    art = _clean_text("\n\n".join(bodies)) if bodies else None
    return _clean_text(best_title), art, best_img


def extract_meta_image(html: str, base_url: str, soup=None) -> Optional[str]:
    if soup is None:
        soup = BeautifulSoup(html, "lxml")
    for m in soup.find_all("meta"):
        key = (m.get("property") or m.get("name") or "").lower()
        if key in {"og:image", "og:image:url", "og:image:secure_url", "twitter:image", "twitter:image:src"}:
            val = m.get("content") or m.get("value")
            if val:
                return urljoin(base_url, val.strip())
    # запасной путь — link rel="image_src"
    link = soup.find("link", rel=lambda x: x and "image_src" in x.lower())
    if link and link.get("href"):
        return urljoin(base_url, link["href"].strip())
    return None


def trafilatura_extract(html: str, url: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        txt = trafilatura.extract(
            html, url=url, config=TRA_CONFIG,
            include_comments=False, include_tables=False,
            favor_recall=True, output="txt",
        )
        data = trafilatura.bare_extraction(html, url=url, config=TRA_CONFIG) or {}
        title = data.get("title")
        return _clean_text(title), _clean_text(txt)
    except Exception:
        return None, None


def readability_extract(html: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        doc = Document(html)
        title = _clean_text(doc.short_title())
        summary_html = doc.summary()
        soup = BeautifulSoup(summary_html, "lxml")
        blocks = []
        for tag in soup.find_all(["h1", "h2", "h3", "p", "li"]):
            t = tag.get_text(" ", strip=True)
            if t and len(t) > 1:
                blocks.append(t)
        text = _clean_text("\n".join(blocks)) if blocks else None
        return title, text
    except Exception:
        return None, None


# ---------- основной пайплайн для одного URL ----------

def grab_one(url: str, min_chars: int = 400, proxy: Optional[str] = None, verbose: bool = False) -> Grab:
    html, err, final_url = fetch_html_smart(url, timeout=25, proxy=proxy, verbose=verbose)
    if not html:
        return Grab(url=final_url, title=None, text=None, image_url=None, source="none", error=err or "no html")

    # Парсим HTML один раз — без этого BeautifulSoup создаёт дерево разбора на каждый вызов
    # extract_jsonld_article / extract_meta_image (до 4 раз для одного и того же HTML).
    _soup = BeautifulSoup(html, "lxml")

    # 1) JSON-LD
    j_title, j_body, j_img = extract_jsonld_article(html, final_url, soup=_soup)
    if verbose:
        print(f"[jsonld] title={'ok' if j_title else 'no'} body_len={len(j_body or '')} img={'ok' if j_img else 'no'}")

    # meta_img вычисляем один раз сразу (раньше вызывался повторно в каждой ветке)
    img = j_img or extract_meta_image(html, final_url, soup=_soup)
    del _soup  # дерево разбора больше не нужно — освобождаем память

    # 2) Trafilatura — запускаем всегда и комбинируем с JSON-LD.
    # JSON-LD articleBody на многих сайтах содержит только анонс; полный текст — в DOM.
    t_title, t_body = trafilatura_extract(html, final_url)
    combo = _combine(t_body, j_body)
    title = t_title or j_title
    if combo and len(combo) >= min_chars:
        src = "combo" if (j_body and t_body) else ("jsonld" if j_body else "trafilatura")
        return Grab(final_url, title, combo, img, source=src)

    # 3) Readability (+ объединяем с JSON-LD); readability_extract использует Document(html),
    # а BS4 применяет только к краткому summary — не к полному HTML, поэтому soup не передаём.
    r_title, r_body = readability_extract(html)
    combo2 = _combine(r_body, combo)
    title2 = r_title or title
    if combo2 and len(combo2) >= min_chars // 2:
        return Grab(final_url, title2, combo2, img, source="readability")

    return Grab(final_url, title or r_title, combo or r_body, img, source="none",
                error="Не удалось получить достаточно текста")


# ---------- CLI ----------

def main(url):
    res = grab_one(url, min_chars=200)

    out = {
        "url": res.url,
        "title": res.title,
        "image_url": res.image_url,
        "text": res.text,
        "source": res.source,
        "error": res.error,
    }

    # Возвращаем текст даже если он короче min_chars (например, короткая заметка).
    # None возвращаем только при полном отсутствии текста.
    if not res.text:
        return None, None
    return out['image_url'], out['text']

if __name__ == "__main__":
    try:
        main('https://thehill.com/homenews/5468923-ty-cobb-bolton-raid-analysis/')
    except KeyboardInterrupt:
        sys.exit(130)
