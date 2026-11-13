"""Lightweight NLP analysis: sentiment scoring, topic classification, summarization.

This is a deterministic, dependency-free analyzer so the demo always works
offline. Swap `analyze_article` for an LLM call later — the interface stays
the same (see `llm.py` for the optional OpenAI-compatible implementation).
"""

import re

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

TOPIC_EMOJI = {
    "Technology": "💻", "Business": "📈", "Science": "🔬",
    "Politics": "🏛️", "Health": "🩺", "World": "🌍", "General": "📰",
}

WORD_RE = re.compile(r"[a-z']+")
STOPWORDS = set(
    "the a an and or but if while of to in on for with at by from as is are was "
    "were be been being it its this that these those he she they them his her "
    "their we our you your not no has have had do does did will would can could "
    "should may might than then so such more most other new new's after before "
    "over under about into out up down said says say report reports amid vs".split()
)


def _tokenize(text: str) -> list[str]:
    return WORD_RE.findall(text.lower())


def score_sentiment(text: str) -> float:
    """Return sentiment in [-1.0, +1.0] using a lexicon with negation handling."""
    tokens = _tokenize(text)
    if not tokens:
        return 0.0

    score = 0.0
    hits = 0
    window: list[str] = []

    for token in tokens:
        window.append(token)
        if len(window) > 3:
            window.pop(0)

        polarity = 0
        if token in POSITIVE_WORDS:
            polarity = 1.0
        elif token in NEGATIVE_WORDS:
            polarity = -1.0
        if polarity == 0:
            continue

        hits += 1
        # Look back for negation / intensifiers within the previous 3 tokens
        context = window[:-1]
        if any(w in NEGATIONS for w in context):
            polarity *= -0.75
        if any(w in INTENSIFIERS for w in context):
            polarity *= 1.4
        score += polarity

    if hits == 0:
        return 0.0
    return max(-1.0, min(1.0, score / max(hits, 1)))


def classify_topic(text: str) -> str:
    """Return the best-matching topic based on keyword frequency."""
    haystack = text.lower()
    best_topic, best_score = "General", 0
    for topic, keywords in TOPIC_KEYWORDS.items():
        score = sum(haystack.count(kw) for kw in keywords)
        if score > best_score:
            best_topic, best_score = topic, score
    return best_topic


def summarize(text: str, max_sentences: int = 2, max_chars: int = 280) -> str:
    """Extractive summary: keep the leading sentences up to the char budget.
    Skips duplicate sentences (common when pages repeat the headline)."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out = ""
    seen: set[str] = set()
    for sentence in sentences:
        key = sentence.strip().lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        if len(out) + len(sentence) > max_chars:
            break
        out += (" " if out else "") + sentence
    return out.strip() or text[:max_chars]


def extract_keywords(text: str, top_n: int = 5) -> list[str]:
    """Simple frequency-based keyword extraction (stopwords removed)."""
    counts: dict[str, int] = {}
    for token in _tokenize(text):
        if token in STOPWORDS or len(token) < 4:
            continue
        counts[token] = counts.get(token, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda x: -x[1])[:top_n]]


def analyze(text: str) -> dict:
    """Run the full analysis pipeline over a piece of text."""
    return {
        "sentiment": round(score_sentiment(text), 3),
        "topic": classify_topic(text),
        "summary": summarize(text),
        "keywords": extract_keywords(text),
    }
