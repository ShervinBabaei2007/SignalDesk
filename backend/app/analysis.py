"""Lightweight NLP analysis: sentiment scoring, topic classification, summarization.

This is a deterministic, dependency-free analyzer so the demo always works
offline. Swap `analyze_article` for an LLM call later — the interface stays
the same (see `llm.py` for the optional OpenAI-compatible implementation).
"""

import re
from collections import Counter

# --- Sentiment lexicons ------------------------------------------------------

POSITIVE_WORDS = {
    "gain", "gains", "growth", "surge", "surged", "record", "profit", "profits",
    "boost", "boosts", "win", "wins", "breakthrough", "success", "successful",
    "innovation", "innovative", "launch", "launched", "expansion", "expands",
    "improve", "improved", "improvement", "strong", "stronger", "beat", "beats",
    "optimistic", "rally", "soar", "soars", "upbeat", "milestone", "award",
    "top", "best", "leading", "advance", "advances", "recovery", "rebound",
}

NEGATIVE_WORDS = {
    "loss", "losses", "decline", "declines", "drop", "drops", "fell", "fall",
    "falls", "crash", "crashes", "crisis", "warning", "warns", "risk", "risks",
    "fear", "fears", "concern", "concerns", "layoff", "layoffs", "cut", "cuts",
    "lawsuit", "sued", "sues", "fine", "fined", "probe", "investigation",
    "scandal", "failure", "failed", "weak", "weaker", "slowdown", "recession",
    "outage", "breach", "hack", "hacked", "attack", "attackers", "fraud",
    "bankruptcy", "default", "shortage", "recall", "criticism", "backlash",
}

# Intensifiers scale the score of adjacent sentiment words
INTENSIFIERS = {"very", "sharply", "significantly", "massively", "deeply", "highly"}

# Negations flip (and soften) the score of a following sentiment word
NEGATIONS = {"not", "no", "never", "without", "hardly", "barely"}

# --- Topic taxonomy ----------------------------------------------------------

TOPIC_KEYWORDS = {
    "Technology": ["ai", "artificial intelligence", "software", "app", "chip",
                   "semiconductor", "cloud", "cyber", "data", "startup", "robot",
                   "quantum", "open source", "algorithm", "gpu", "cpu"],
    "Business": ["market", "markets", "revenue", "earnings", "ipo", "merger",
                 "acquisition", "stocks", "shares", "investors", "economy",
                 "inflation", "interest rate", "gdp", "ceo", "company"],
    "Science": ["research", "study", "scientists", "climate", "space", "nasa",
                "discovery", "physics", "biology", "gene", "telescope", "energy"],
    "Politics": ["election", "government", "senate", "congress", "president",
                 "policy", "regulation", "law", "court", "vote", "minister",
                 "parliament", "sanctions", "treaty"],
    "Health": ["health", "fda", "vaccine", "disease", "cancer", "hospital",
               "medical", "drug", "clinical", "patients", "virus", "outbreak"],
    "World": ["war", "conflict", "ukraine", "gaza", "military", "border",
              "refugees", "united nations", "diplomacy", "protest", "earthquake",
              "flood", "hurricane"],
}

# Icon shown next to each topic in the UI
TOPIC_EMOJI = {
    "Technology": "💻", "Business": "📈", "Science": "🔬",
    "Politics": "🏛️", "Health": "🩺", "World": "🌍", "General": "📰",
}

WORD_RE = re.compile(r"[a-z']+")  # lowercase words, keeping apostrophes ("don't")
# Common words that carry no topical meaning, excluded from keywords
STOPWORDS = set(
    "the a an and or but if while of to in on for with at by from as is are was "
    "were be been being it its this that these those he she they them his her "
    "their we our you your not no has have had do does did will would can could "
    "should may might than then so such more most other new new's after before "
    "over under about into out up down said says say report reports amid vs".split()
)


def _tokenize(text: str) -> list[str]:
    """Lowercase text into word tokens."""
    return WORD_RE.findall(text.lower())


def score_sentiment(text: str) -> float:
    """Return sentiment in [-1.0, +1.0] using a lexicon with negation handling."""
    tokens = _tokenize(text)
    if not tokens:
        return 0.0

    score = 0.0
    hits = 0
    window: list[str] = []

    # Score each sentiment word, adjusted by negations/intensifiers just before it.
    for token in tokens:
        window.append(token)
        if len(window) > 3:  # keep the current token plus the two before it
            window.pop(0)

        if token in POSITIVE_WORDS:
            polarity = 1.0
        elif token in NEGATIVE_WORDS:
            polarity = -1.0
        else:
            continue

        hits += 1
        # Look back for negation / intensifiers within the previous 2 tokens
        context = window[:-1]
        if any(w in NEGATIONS for w in context):
            polarity *= -0.75
        if any(w in INTENSIFIERS for w in context):
            polarity *= 1.4
        score += polarity

    if hits == 0:
        return 0.0
    return max(-1.0, min(1.0, score / hits))


def classify_topic(text: str) -> str:
    """Return the best-matching topic based on keyword frequency."""
    haystack = text.lower()
    best_topic, best_score = "General", 0
    # Count keyword occurrences per topic and keep the highest (first wins ties).
    for topic, keywords in TOPIC_KEYWORDS.items():
        score = sum(haystack.count(kw) for kw in keywords)
        if score > best_score:
            best_topic, best_score = topic, score
    return best_topic


# Page furniture that survives HTML extraction and ends up inside summaries.
_BOILERPLATE = [re.compile(p, re.IGNORECASE) for p in (
    # \s+ between words: extracted page text often has line breaks inside these phrases
    r"Story\s+text\s+Size\s+Width\s+Links\s*\*?\s*Subscribers\s+only\s+Learn\s+more",
    r"Skip\s+Navigation(?:\s+(?:Markets|Business|Investing(?:\s+Club)?|Tech|Politics(?:\s+&\s+Policy)?|Video"
    r"|Watchlist|PRO|Livestream|Menu|Key\s+Points|Related\s+Stories|Search))*",
    # dateline, image-caption, "published N ago" and photo-credit furniture
    r"In\s+Brief\s+Posted:\s*[^.]{0,80}?\d{4}",
    r"Image\s+source,\s*[^.]{0,160}?Image\s+caption,\s*",
    r"Published\s+\d+\s+(?:minutes?|hours?)\s+ago",
    r"(?:Image|Photo)\s+credits?:\s*[^.]{0,120}?(?:Getty\s+Images|Anadolu|Reuters|AFP|AP\s+Photo|Bloomberg)",
    # share-button rows ("Facebook Twitter Pinterest LinkedIn Email"), teaser labels and stock-photo credits
    r"\b(?:Facebook|Twitter|Pinterest|LinkedIn|WhatsApp|Reddit|Email|Print|Share)(?:\s+(?:Facebook|Twitter|Pinterest|LinkedIn|WhatsApp|Reddit|Email|Print|Share)){2,}\b",
    r"\bFULL\s+STORY\b",
    r"\bCredit:\s*(?:Shutterstock|Getty\s+Images|Alamy|iStock|Adobe\s+Stock)\b",
)]


def has_boilerplate(text: str) -> bool:
    """True when the text contains scraped navigation, paywall or credit furniture."""
    return any(p.search(text) for p in _BOILERPLATE)


def strip_boilerplate(text: str) -> str:
    """Remove scraped navigation, paywall and credit furniture from article text."""
    for pattern in _BOILERPLATE:
        text = pattern.sub(" ", text)
    # Collapse the runs of spaces left behind, keeping line breaks.
    return re.sub(r"[ \t]{2,}", " ", text)


def summarize(text: str, max_sentences: int = 2, max_chars: int = 280,
              avoid: str | None = None) -> str:
    """Extractive summary: keep the leading sentences up to the char budget.

    Skips duplicate sentences and sentences that merely restate `avoid`
    (usually the headline, which the UI already shows).
    """
    text = re.sub(r"\s+", " ", strip_boilerplate(text)).strip()
    if len(text) <= max_chars:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)  # split after sentence-ending punctuation
    out = ""
    seen: set[str] = set()
    # Append sentences in order until the budget is reached, skipping repeats and headline restatements.
    for sentence in sentences:
        key = sentence.strip().lower()[:80]  # first 80 chars identify near-identical sentences
        if key in seen:
            continue
        seen.add(key)
        if avoid and _overlap(sentence, avoid) > 0.6:
            continue
        if len(out) + len(sentence) > max_chars:
            break
        out += (" " if out else "") + sentence
    return out.strip() or text[:max_chars]


# --- Structured (skimmable) summary ------------------------------------------

# Sentences that are feed/page boilerplate rather than article content
_JUNK_SENTENCE = re.compile(
    r"(appeared first on|read more|continue reading|share this|advertisement|"
    r"all rights reserved|photo credit|image credit|image:)", re.IGNORECASE)
_QUOTE_CHARS = "“”\"«»"
_NUMBER_HINT = re.compile(r"(\d+%|[$€£]\s?\d|\b\d[\d.,]*\b)")  # percentages, money amounts or plain numbers
_WORD = re.compile(r"[a-zA-Z']{3,}")  # words of 3+ letters, ignoring short filler


def _overlap(a: str, b: str) -> float:
    """Word-overlap ratio between two strings (0..1)."""
    aw = set(_WORD.findall(a.lower()))
    bw = set(_WORD.findall(b.lower()))
    if not aw or not bw:
        return 0.0
    return len(aw & bw) / min(len(aw), len(bw))


def _clean_sentences(text: str) -> list[str]:
    """Split article text into clean, informative sentences with boilerplate and junk removed."""
    text = re.sub(r"\s+", " ", strip_boilerplate(text)).strip()
    out = []
    # Keep sentences of a readable length (40-420 chars) that are not junk.
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        sentence = sentence.strip()
        if 40 <= len(sentence) <= 420 and not _JUNK_SENTENCE.search(sentence):
            out.append(sentence)
    return out


def _has_quote(sentence: str) -> bool:
    """True when the sentence contains a quotation mark."""
    return any(c in sentence for c in _QUOTE_CHARS)


def _score_sentence(sentence: str, position: float) -> float:
    """Information-density heuristic for ranking sentences as key points."""
    score = 1.0
    if _NUMBER_HINT.search(sentence):
        score += 1.5
    if _has_quote(sentence):
        score += 1.0
    # prefer sentences in the informative first half of the body
    score += max(0.0, 0.8 - position) * 1.2
    words = _WORD.findall(sentence)
    # longer sentences carry more information, capped at 32 words
    score += min(len(words), 32) / 32 * 0.8
    return score


def structured_summary(text: str, title: str = "", max_points: int = 6) -> str:
    """Build a skimmable, sectioned brief from an article's full text.

    Sections:

    ## TL;DR           — 1-2 leading sentences that say something new
    ## Key points      — the most information-dense sentences as bullets
    ## By the numbers  — sentences containing figures/statistics
    ## Notable quotes  — direct quotes from the piece
    ## Bottom line     — the closing takeaway

    Sections are emitted in a light markdown-ish format ("## Heading",
    "- bullet") that the frontend renders with clear hierarchy.
    """
    sentences = _clean_sentences(text)
    if not sentences:
        return ""
    n = len(sentences)
    used: list[str] = []
    sections: list[tuple[str, list[str], bool]] = []  # (heading, items, is_bullets)

    def is_used(sentence: str) -> bool:
        """True when a sentence largely repeats one already chosen."""
        return any(_overlap(sentence, u) > 0.55 for u in used)

    # TL;DR — lead the reader with the first sentences that aren't just the
    # headline restated (the title is already on screen).
    lead: list[str] = []
    lead_chars = 0
    # Look only at the first 6 sentences and stop once ~200 chars are collected.
    for sentence in sentences[:6]:
        if title and _overlap(sentence, title) > 0.65:
            continue
        if is_used(sentence):
            continue
        lead.append(sentence)
        used.append(sentence)
        lead_chars += len(sentence)
        if lead_chars >= 200:
            break
    if lead:
        sections.append(("TL;DR", lead, False))

    # Rank the remaining sentences once, then pull different views from it
    ranked = sorted(
        ((i, s, _score_sentence(s, i / n)) for i, s in enumerate(sentences)),
        key=lambda t: -t[2],
    )
    remaining = [(s, i) for i, s, _ in ranked if not is_used(s)]

    def take(pred, count):
        """Pick up to `count` unused sentences that satisfy `pred`."""
        picked = []
        # Walk sentences best-score first.
        for s, i in remaining:
            if not pred(s) or is_used(s):
                continue
            picked.append((s, i))
            used.append(s)
            if len(picked) >= count:
                break
        return picked

    if not lead:  # every lead sentence restated the title: fall back to plain key points
        points = take(lambda s: True, max_points)
        sections.append(("Key points", [s for s, _ in points], True))
    else:
        # Key points — top general-information sentences (numbers/quotes go
        # to their own sections so they don't dominate)
        points = take(lambda s: not _NUMBER_HINT.search(s) and not _has_quote(s), max_points)
        if len(points) < 2:  # short articles: allow anything
            points = take(lambda s: True, max_points - len(points))
        if points:
            sections.append(("Key points", [s for s, _ in points], True))

        numbers = take(lambda s: bool(_NUMBER_HINT.search(s)) and not _has_quote(s), 3)
        if numbers:
            sections.append(("By the numbers", [s for s, _ in numbers], True))

        quotes = take(_has_quote, 2)
        if quotes:
            sections.append(("Notable quotes", [s for s, _ in quotes], True))

    # Bottom line — closing takeaway from the end of the piece
    for sentence in reversed(sentences[-4:]):
        if not is_used(sentence) and len(sentence) > 60:
            sections.append(("Bottom line", [sentence], False))
            used.append(sentence)
            break

    if not sections:
        return ""
    lines = []
    # Render each section as a "## Heading" followed by bullets or plain lines.
    for heading, items, is_bullets in sections:
        lines.append(f"## {heading}")
        for item in items:
            lines.append(f"- {item}" if is_bullets else item)
    return "\n".join(lines)


def extract_keywords(text: str, top_n: int = 5) -> list[str]:
    """Simple frequency-based keyword extraction (stopwords removed)."""
    # Count meaningful words of 4+ letters.
    counts = Counter(t for t in _tokenize(strip_boilerplate(text))
                     if t not in STOPWORDS and len(t) >= 4)
    return [w for w, _ in counts.most_common(top_n)]


def analyze(text: str) -> dict:
    """Run the full analysis pipeline over a piece of text."""
    return {
        "sentiment": round(score_sentiment(text), 3),
        "topic": classify_topic(text),
        "summary": summarize(text),
        "keywords": extract_keywords(text),
    }
