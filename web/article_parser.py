# pip install requests beautifulsoup4 lxml
from __future__ import annotations

import json
from typing import Optional, Dict, Any, List

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ---------------- HTTP ----------------
def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "he-IL,he;q=0.9,en;q=0.8,ru;q=0.7",
        "Referer": "https://www.ynet.co.il/",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(403, 429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


def fetch_html(url: str, timeout: int = 20, session: Optional[requests.Session] = None) -> str:
    sess = session or make_session()
    r = sess.get(url, timeout=timeout, allow_redirects=True)
    # Если сервер вернул 403 — иногда помогает другой Referer/повтор
    if r.status_code == 403:
        sess.headers["Referer"] = "https://www.google.com/"
        r = sess.get(url, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    r.encoding = r.encoding or "utf-8"
    return r.text


# ---------------- Parsing helpers ----------------
def _clean(s: Optional[str]) -> str:
    if not s:
        return ""
    return " ".join(s.split())


def _try_jsonld_article(soup: BeautifulSoup) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue

        candidates = data if isinstance(data, list) else [data]
        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            jtype = obj.get("@type")
            types: List[str] = []
            if isinstance(jtype, str):
                types = [jtype]
            elif isinstance(jtype, list):
                types = [t for t in jtype if isinstance(t, str)]
            if "NewsArticle" not in types:
                continue

            out["title"] = _clean(obj.get("headline"))
            out["subtitle"] = _clean(obj.get("description"))
            out["author"] = (
                _clean(obj.get("author", {}).get("name"))
                if isinstance(obj.get("author"), dict)
                else _clean(obj.get("author"))
            )
            out["published"] = _clean(obj.get("datePublished"))
            out["updated"] = _clean(obj.get("dateModified"))
            out["text"] = _clean(obj.get("articleBody"))
            if out.get("text"):
                return out
    return out


def _fallback_from_dom(soup: BeautifulSoup) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    html = soup.find("html")
    out["lang"] = (html.get("lang") if html else "") or ""

    h1 = soup.select_one(".ArticleHeaderComponent1280 .mainTitle") or soup.select_one("h1.mainTitle")
    out["title"] = _clean(h1.get_text(" ", strip=True)) if h1 else ""

    sub = soup.select_one(".subTitleWrapper .subTitle")
    out["subtitle"] = _clean(sub.get_text(" ", strip=True)) if sub else ""

    author = (soup.select_one('meta[property="vr:author"]') or
              soup.select_one(".authoranddate .authors a"))
    out["author"] = _clean(author.get("content") if author and author.has_attr("content")
                           else author.get_text(" ", strip=True) if author else "")

    dt = (soup.select_one('meta[property="article:published_time"]') or
          soup.select_one("time[datetime]"))
    out["published"] = _clean(dt.get("content") if dt and dt.has_attr("content")
                              else dt.get("datetime") if dt and dt.has_attr("datetime")
                              else "")

    paras = []
    for p in soup.select('#ArticleBodyComponent .text_editor_paragraph'):
        txt = _clean(p.get_text(" ", strip=True))
        if txt:
            paras.append(txt)
    out["text"] = "\n".join(paras)

    if not out["text"]:
        body = soup.select_one("#ArticleBodyComponent") or soup
        out["text"] = _clean(body.get_text(" ", strip=True))

    return out


def extract_ynet_article_from_html(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    data = {
        "lang": (soup.find("html").get("lang") if soup.find("html") else "") or ""
    }

    j = _try_jsonld_article(soup)
    data.update({k: v for k, v in j.items() if v})

    need_text = not data.get("text")
    need_title = not data.get("title")
    if need_text or need_title or not data.get("author") or not data.get("published"):
        d = _fallback_from_dom(soup)
        for k, v in d.items():
            if not data.get(k) and v:
                data[k] = v

    for key in ["title", "subtitle", "author", "published", "updated", "text", "lang"]:
        data[key] = _clean(data.get(key, ""))

    return data


# ---------------- Public API ----------------
def extract_ynet_article(url: str, timeout: int = 20) -> Dict[str, Any]:
    """
    Загружает страницу по URL и возвращает словарь с полями:
    {title, subtitle, author, published, updated, text, lang}
    """
    html = fetch_html(url, timeout=timeout)
    return extract_ynet_article_from_html(html)


# ---------------- Demo ----------------
if __name__ == "__main__":
    url = "https://www.ynet.co.il/news/article/rj0mrzvlkl"
    article = extract_ynet_article(url)
    import pprint
    pprint.pprint(article, width=120, compact=True)
