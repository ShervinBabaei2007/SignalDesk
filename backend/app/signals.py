"""Transparency signals read from an article's page.

These are facts about how an outlet presents a story, not a judgement of its truthfulness: is the
author named, is the publication (and any update) dated, does the text link out to what it relies
on, does the page point to a corrections or standards policy, and does the article itself carry a
correction notice. :mod:`app.reliability` turns them into per-outlet figures.

Dependency-free, like :mod:`app.extractor`, and tolerant of bad markup: every check is a plain
pattern over the HTML and a missing signal simply counts as absent.
"""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import urlparse

_META_TAG = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_ATTR = re.compile(r"""([a-zA-Z:_.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_PARAGRAPH = re.compile(r"<p\b[^>]*>(.*?)</p\s*>", re.IGNORECASE | re.DOTALL)
_ANCHOR = re.compile(r"<a\b([^>]*)>(.*?)</a\s*>", re.IGNORECASE | re.DOTALL)
_HREF = re.compile(r"""href\s*=\s*["'](https?://[^"']+)["']""", re.IGNORECASE)
_DROP = re.compile(r"<(script|style|noscript|svg)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")

_AUTHOR_META = {"author", "article:author", "og:article:author", "parsely-author", "dc.creator", "byl", "sailthru.author"}
_PUBLISHED_META = {"article:published_time", "og:article:published_time", "datepublished", "pubdate",
                   "dc.date.issued", "parsely-pub-date", "publish-date", "date"}
_MODIFIED_META = {"article:modified_time", "og:updated_time", "datemodified", "last-modified", "dc.date.modified"}
_BYLINE_CLASS = re.compile(r"""class\s*=\s*["'][^"']*\b(byline|author|writer)\b[^"']*["']""", re.IGNORECASE)
_AUTHOR_MARKUP = re.compile(r"""(itemprop|rel)\s*=\s*["']author["']|"author"\s*:\s*[\[{"]""", re.IGNORECASE)
_JSON_PUBLISHED = re.compile(r'"datePublished"\s*:\s*"([^"]+)"')
_JSON_MODIFIED = re.compile(r'"dateModified"\s*:\s*"([^"]+)"')
_ITEMPROP_PUBLISHED = re.compile(r"""itemprop\s*=\s*["']datePublished["'][^>]*?(?:content|datetime)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_TIME_TAG = re.compile(r"""<time\b[^>]*datetime\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_POLICY = re.compile(
    r"corrections?\b|editorial[\s-]+(standards|policy|guidelines)|ethics[\s-]+(policy|code)|"
    r"standards[\s-]+(and|&)[\s-]+ethics|fact[\s-]?check(ing)?[\s-]+policy", re.IGNORECASE)
_CORRECTION_NOTICE = re.compile(
    r"(?:^|\n)\s*(?:correction|clarification|editor'?s note)\s*[:–—-]|"
    r"this (?:article|story) (?:has been|was) corrected|an earlier version of this (?:article|story)|"
    r"(?:a|the) (?:previous|earlier) version of this (?:article|story)|has been (?:corrected|updated to correct)",
    re.IGNORECASE)
_SOCIAL = ("facebook.", "twitter.", "x.com", "t.co", "instagram.", "linkedin.", "pinterest.", "whatsapp.",
           "youtube.", "youtu.be", "tiktok.", "reddit.", "telegram.", "flipboard.", "mailto")
MAX_SOURCES = 10


def _attrs(tag: str) -> dict[str, str]:
    """Attributes of an HTML tag as a lowercase-keyed dict."""
    return {m.group(1).lower(): unescape(m.group(2) if m.group(2) is not None else m.group(3))
            for m in _ATTR.finditer(tag)}


def _host(url: str) -> str:
    """Host of a URL without a leading www."""
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def has_correction_notice(text: str) -> bool:
    """True when the article text carries a correction, clarification or earlier-version notice."""
    return bool(_CORRECTION_NOTICE.search(text or ""))


def extract_signals(html: str, base_url: str = "", text: str = "") -> dict:
    """Transparency signals of a page: byline, dates, sourcing links, a corrections policy, a correction notice."""
    head = html[:400_000]
    metas: dict[str, str] = {}
    for tag in _META_TAG.findall(head):
        a = _attrs(tag)
        key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
        if key and a.get("content"):
            metas.setdefault(key, a["content"].strip())

    byline = any(metas.get(k) for k in _AUTHOR_META) or bool(_AUTHOR_MARKUP.search(head)) or bool(_BYLINE_CLASS.search(head))
    published = next((metas[k] for k in _PUBLISHED_META if metas.get(k)), None)
    if not published:
        match = _JSON_PUBLISHED.search(head) or _ITEMPROP_PUBLISHED.search(head) or _TIME_TAG.search(head)
        published = match.group(1) if match else None
    modified = next((metas[k] for k in _MODIFIED_META if metas.get(k)), None)
    if not modified:
        match = _JSON_MODIFIED.search(head)
        modified = match.group(1) if match else None

    body = _DROP.sub(" ", head)
    own = _host(base_url)
    domains: set[str] = set()
    for paragraph in _PARAGRAPH.findall(body):
        for href in _HREF.findall(paragraph):
            host = _host(href)
            if host and host != own and not host.endswith("." + own) and not any(s in host for s in _SOCIAL):
                domains.add(host)
    policy = any(_POLICY.search(_TAGS.sub(" ", inner)) or _POLICY.search(_attrs(attrs).get("href", ""))
                 for attrs, inner in _ANCHOR.findall(body))

    return {
        "byline": byline,
        "published": bool(published),
        "updated": bool(modified and modified != published),
        "sources": min(len(domains), MAX_SOURCES),
        "policy": policy,
        "correction": has_correction_notice(text),
    }
