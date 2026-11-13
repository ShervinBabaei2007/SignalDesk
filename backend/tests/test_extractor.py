"""Unit tests for HTML main-text extraction."""

from app.extractor import extract_main_text
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
    text = extract_main_text(HTML)
    assert "charges in under five minutes" in text
    assert "manufacturing could begin" in text


def test_drops_scripts_and_styles():
    text = extract_main_text(HTML)
    assert "var x" not in text
    assert "color: red" not in text


def test_drops_navigation_and_footer():
    text = extract_main_text(HTML)
    assert "Sign in" not in text
    assert "Privacy Policy" not in text
    assert "Related Articles" not in text


def test_handles_empty_and_non_html():
    assert extract_main_text("") == ""
    assert extract_main_text("<div></div>") == ""
    assert "hello" in extract_main_text("<p>hello</p>")


def test_prefers_article_block():
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
    hn = "Some title. Article URL: https://x.com/y Comments URL: https://a Points: 5 # Comments"
    assert strip_feed_metadata(hn) == "Some title."
    assert strip_feed_metadata("normal text") == "normal text"
