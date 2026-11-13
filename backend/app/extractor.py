"""HTML main-text extraction.

Pulls the readable article text out of a raw HTML page: drops scripts,
styles, navigation/boilerplate blocks, then converts the rest to plain text.
Dependency-free so it works everywhere the rest of the analyzer works.
"""

import re
from html import unescape

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
_BLANK_LINES = re.compile(r"\n{3,}")
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
        text_len = len(re.sub(r"<[^>]+>", " ", inner).strip())
        if text_len > best_len:
            best_block, best_len = inner, text_len

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
