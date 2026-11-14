"""Unit tests for HTML main-text extraction."""

from app.analysis import structured_summary
from app.extractor import extract_image_url, extract_main_text
from app.ingestion import strip_feed_metadata


HTML = """
<html>
<head><style>body { color: red; }</style><script>var x = 1;</script></head>
<body>
<nav><a href="/">Home</a> <a href="/about">About</a> Sign in</nav>
<header><h1>Site Brand</h1></header>
<article>
  <h1>Scientists Discover New Battery Breakthrough</h1>
  <p>Researchers announced a battery that charges in under five minutes and
  lasts twice as long as lithium-ion cells.</p>
  <p>The team says manufacturing could begin next year.</p>
</article>
<aside>Related Articles</aside>
<footer>All rights reserved. Privacy Policy</footer>
</body>
</html>
"""


def test_extracts_body_text():
    """Body text is extracted from the page."""
    text = extract_main_text(HTML)
    assert "charges in under five minutes" in text
    assert "manufacturing could begin" in text


def test_drops_scripts_and_styles():
    """Scripts and styles are dropped."""
    text = extract_main_text(HTML)
    assert "var x" not in text
    assert "color: red" not in text


def test_drops_navigation_and_footer():
    """Navigation and footer blocks are dropped."""
    text = extract_main_text(HTML)
    assert "Sign in" not in text
    assert "Privacy Policy" not in text
    assert "Related Articles" not in text


def test_handles_empty_and_non_html():
    """Empty and non-HTML input yields empty text."""
    assert extract_main_text("") == ""
    assert extract_main_text("<div></div>") == ""
    assert "hello" in extract_main_text("<p>hello</p>")


def test_prefers_article_block():
    """An <article> block is preferred over the rest of the page."""
    page = """
    <html><body>
    <header>Sign in Subscribe Newsletter Skip to main content junk junk</header>
    <article><p>The real story: scientists found a new exoplanet orbiting a
    nearby star with strong signs of an atmosphere.</p></article>
    <footer>All rights reserved</footer>
    </body></html>"""
    text = extract_main_text(page)
    assert "exoplanet" in text
    assert "Newsletter" not in text
    assert "All rights reserved" not in text


def test_strip_feed_metadata():
    """Feed metadata furniture is stripped from the text."""
    hn = "Some title. Article URL: https://x.com/y Comments URL: https://a Points: 5 # Comments"
    assert strip_feed_metadata(hn) == "Some title."
    assert strip_feed_metadata("normal text") == "normal text"


def test_structured_summary_sections():
    """The structured summary has its expected sections."""
    body = (
        "OpenAI released a new browser today with built-in agent features. "
        "The company says the browser will ship to all users next month, and it "
        "includes an assistant that can complete purchases on the user's behalf. "
        "Privacy groups immediately criticized the move as risky for consumers. "
        "The launch follows two years of declining search traffic across the web. "
        "Analysts estimate the browser could reach 100 million users within a year. "
        "\"We built this because people deserve a faster web,\" said the CEO at the "
        "launch event in San Francisco on Tuesday. The browser is free and open to "
        "everyone starting next week. Regulators in the EU are reportedly reviewing "
        "the feature set for compliance concerns."
    )
    title = "OpenAI launches a browser with agent features"
    result = structured_summary(body, title)
    assert result.startswith("## TL;DR")
    assert "## Key points" in result
    assert "## By the numbers" in result
    assert "## Notable quotes" in result
    assert title not in result  # never parrot the headline
    assert result.count("- ") >= 4


def test_structured_summary_short_text():
    """Short text produces a short structured summary."""
    assert structured_summary("Too short.") == ""


def test_extract_image_url_prefers_og_and_resolves_relative():
    """The og:image is preferred and relative URLs are resolved."""
    html = '<head><meta name="twitter:image" content="http://t.example/t.jpg">' \
           '<meta property="og:image" content="/img/a.jpg?x=1&amp;y=2"></head>'
    assert extract_image_url(html, "https://news.example/story") == "https://news.example/img/a.jpg?x=1&y=2"


def test_extract_image_url_fallbacks_and_rejects_unsafe():
    """Image fallbacks work and unsafe URLs are rejected."""
    assert extract_image_url('<meta name="twitter:image" content="https://a.example/t.png">') == "https://a.example/t.png"
    assert extract_image_url('<link rel="image_src" href="https://a.example/l.png">') == "https://a.example/l.png"
    assert extract_image_url('<meta property="og:image" content="javascript:alert(1)">') is None
    assert extract_image_url('<meta property="og:image" content="data:image/png;base64,AAAA">') is None
    assert extract_image_url("<p>nothing</p>") is None
