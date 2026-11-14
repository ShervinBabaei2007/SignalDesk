"""HTML main-text extraction.

Pulls the readable article text out of a raw HTML page: drops scripts,
styles, navigation/boilerplate blocks, then converts the rest to plain text.
Dependency-free so it works everywhere the rest of the analyzer works.
"""

import re
from html import unescape
from urllib.parse import urljoin

# Blocks that never contain article body text
_DROP_BLOCKS = re.compile(
    r"<(script|style|noscript|svg|iframe|form|template|button|select|textarea)\b.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
# Structural boilerplate (nav bars, footers, sidebars)
_DROP_BOILERPLATE = re.compile(
    r"<(nav|footer|header|aside|menu)\b[^>]*>.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
# HTML comments
_COMMENTS = re.compile(r"<!--.*?-->", re.DOTALL)
# Block-level boundaries become newlines so paragraph structure survives
_BLOCK_BOUNDARY = re.compile(
    r"<(?:br|/p|/div|/li|/h[1-6]|/tr|/blockquote|/section|/article)[^>]*>",
    re.IGNORECASE,
)
_ANY_TAG = re.compile(r"<[^>]+>")
_INLINE_WS = re.compile(r"[ \t]+")
_BLANK_LINES = re.compile(r"\n{3,}")  # three or more newlines collapse to one blank line
# Common UI noise patterns found in extracted lines
_NOISE_LINE = re.compile(
    r"^(share|sign in|sign up|log in|subscribe|newsletter|cookie|accept all|"
    r"advertisement|related articles?|read more|skip to (main )?content|menu|"
    r"follow us|all rights reserved|terms of (service|use)|privacy policy)\b.*$",
    re.IGNORECASE,
)


def extract_main_text(html: str, max_chars: int = 10000) -> str:
    """Return the readable text content of an HTML page.

    Prefers the page's <article>/<main> block when present (most news sites
    wrap the story there), which skips site headers, promos and nav junk.
    """
    # Prefer the largest <article> or <main> container if one exists
    best_block = None
    best_len = 0
    for match in re.finditer(
        r"<(article|main)\b[^>]*>(.*?)</\1\s*>", html, re.IGNORECASE | re.DOTALL
    ):
        inner = match.group(2)
        # crude content score: real articles have lots of text
        text_len = len(_ANY_TAG.sub(" ", inner).strip())
        if text_len > best_len:
            best_block, best_len = inner, text_len

    # a container under 400 chars is likely a teaser, so fall back to the whole page
    source = best_block if best_block and best_len > 400 else html

    text = _COMMENTS.sub(" ", source)
    text = _DROP_BLOCKS.sub(" ", text)
    text = _DROP_BOILERPLATE.sub(" ", text)
    # Phrase-level boilerplate that appears inline
    for phrase in ("Skip to main content", "Skip to content", "Advertisement",
                   "Share this article", "Share this post"):
        text = text.replace(phrase, " ")
    text = _BLOCK_BOUNDARY.sub("\n", text)
    text = _ANY_TAG.sub(" ", text)
    text = unescape(text)

    lines = []
    # Normalize each line and drop separators and short UI-noise lines.
    for raw_line in text.split("\n"):
        line = _INLINE_WS.sub(" ", raw_line).strip()
        if len(line) < 3:  # separators, empty lines
            continue
        if _NOISE_LINE.match(line) and len(line) < 80:
            continue
        lines.append(line)

    result = "\n".join(lines)
    result = _BLANK_LINES.sub("\n\n", result)
    return result[:max_chars]


_META_TAG = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_LINK_TAG = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
_ATTR = re.compile(r"""([a-zA-Z:_-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")  # name="value" or name='value'
# Image meta keys in order of preference
_IMAGE_META_KEYS =("og:image:secure_url", "og:image", "twitter:image", "twitter:image:src")


def _attrs(tag: str) -> dict[str, str]:
    """Parse an HTML tag's attributes into a lowercase-keyed dict."""
    return {m.group(1).lower(): unescape(m.group(2) if m.group(2) is not None else m.group(3))
            for m in _ATTR.finditer(tag)}


def clean_image_url(candidate: str | None, base_url: str = "") -> str | None:
    """Resolve to an absolute http(s) URL, or None if unusable."""
    if not candidate:
        return None
    url = urljoin(base_url, candidate.strip())
    # Reject data:/javascript: URLs and anything too long for the image_url column.
    if not url.lower().startswith(("http://", "https://")) or len(url) > 1000:
        return None
    return url


def extract_image_url(html: str, base_url: str = "") -> str | None:
    """Lead image of a page: og:image, then twitter:image, then rel=image_src."""
    head = html[:200_000]  # meta tags live near the top; skip scanning huge bodies
    found: dict[str, str] = {}
    # Remember the first value seen for each image meta key.
    for tag in _META_TAG.findall(head):
        a = _attrs(tag)
        key = (a.get("property") or a.get("name") or "").lower()
        if key in _IMAGE_META_KEYS and a.get("content") and key not in found:
            found[key] = a["content"]
    # Try the keys in preference order.
    for key in _IMAGE_META_KEYS:
        url = clean_image_url(found.get(key), base_url)
        if url:
            return url
    # Last resort: the older <link rel="image_src"> convention.
    for tag in _LINK_TAG.findall(head):
        a = _attrs(tag)
        if a.get("rel", "").lower() == "image_src":
            url = clean_image_url(a.get("href"), base_url)
            if url:
                return url
    return None
