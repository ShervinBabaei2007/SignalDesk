"""Optional LLM-backed article analysis.

The deterministic lexicon analyzer in :mod:`app.analysis` is always used as
the baseline. When ``LLM_ENABLED`` is set (and an API key / local endpoint is
configured) enrichment asks a model for a structured analysis and upgrades the
article with a written TL;DR, key points, a "why it matters" explanation,
importance/relevance scores, and cleaner keywords.

Any OpenAI-compatible endpoint works:

    # OpenAI
    LLM_ENABLED=true
    LLM_API_KEY=sk-...
    LLM_MODEL=gpt-4o-mini

    # Ollama (local, no key needed)
    LLM_ENABLED=true
    LLM_BASE_URL=http://localhost:11434/v1
    LLM_MODEL=llama3.1

The provider interface is intentionally tiny so another backend can be added
without touching ingestion or enrichment code. Model output is validated and
normalized here; malformed responses never raise, they just fall back to the
deterministic analysis.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from . import config

logger = logging.getLogger("signaldesk.llm")

# Map the richer taxonomy from the analysis prompt onto SignalDesk's topics.
_CATEGORY_MAP = {
    "artificial_intelligence": "Technology",
    "software_engineering": "Technology",
    "computer_science": "Technology",
    "cybersecurity": "Technology",
    "hardware": "Technology",
    "business": "Business",
    "finance": "Business",
    "science": "Science",
    "health": "Health",
    "politics": "Politics",
    "world": "World",
    "formula_one": "World",
    "other": "General",
}

VALID_TOPICS = {"Technology", "Business", "Science", "Politics", "Health", "World", "General"}
VALID_CONTENT_TYPES = {"announcement", "report", "analysis", "opinion", "speculation", "other"}

SYSTEM_PROMPT = """You are an analytical research assistant for a technology and \
current-events intelligence platform.

Analyze the supplied article using only the information provided. Do not invent \
facts, statistics, quotes, or events. If the text is only a feed excerpt, do not \
imply you read the full article.

Return valid JSON with exactly these fields:
{
  "category": "artificial_intelligence | software_engineering | computer_science | cybersecurity | hardware | business | finance | science | health | politics | world | formula_one | other",
  "summary": "A concise, factual TL;DR of 2-3 sentences.",
  "key_points": ["3-6 important facts or developments"],
  "why_it_matters": "One or two sentences explaining the significance.",
  "implications": ["0-3 likely implications for developers, businesses, or consumers"],
  "importance_score": 1-10,
  "relevance_score": 1-10,
  "sentiment": -1.0 to 1.0,
  "content_type": "announcement | report | analysis | opinion | speculation | other",
  "tags": ["3-6 short keywords"]
}

Do not include Markdown fences or commentary outside the JSON."""


def available() -> bool:
    """True when LLM analysis is enabled and an endpoint is reachable by config."""
    if not config.LLM_ENABLED:
        return False
    if config.LLM_API_KEY:
        return True
    # Local OpenAI-compatible servers (Ollama, LM Studio) need no key.
    return "api.openai.com" not in config.LLM_BASE_URL


def _extract_json(text: str) -> dict[str, Any] | None:
    """Parse a JSON object out of a model response, tolerating fences/prose."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _clean_str(value: Any, max_len: int) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()[:max_len]


def _clean_list(value: Any, max_items: int, max_len: int = 300) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _clean_str(item, max_len)
        if text:
            out.append(text)
        if len(out) >= max_items:
            break
    return out


def _clamp(value: Any, low: float, high: float, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def normalize_analysis(data: dict[str, Any]) -> dict[str, Any] | None:
    """Validate and normalize raw model JSON into SignalDesk's shape.

    Returns None when the response is unusable (e.g. no summary at all).
    """
    if not isinstance(data, dict):
        return None

    summary = _clean_str(data.get("summary") or data.get("tldr"), 900)
    if len(summary) < 20:
        return None

    raw_category = _clean_str(data.get("category") or data.get("topic"), 60).lower()
    topic = _CATEGORY_MAP.get(raw_category, raw_category.title())
    if topic not in VALID_TOPICS:
        topic = "General"

    content_type = _clean_str(data.get("content_type"), 40).lower()
    if content_type not in VALID_CONTENT_TYPES:
        content_type = "other"

    tags = _clean_list(data.get("tags") or data.get("keywords"), 6, 60)
    keywords = [t for t in tags if len(t) >= 3][:5]

    return {
        "topic": topic,
        "sentiment": round(_clamp(data.get("sentiment"), -1.0, 1.0, 0.0), 3),
        "summary": summary,
        "key_points": _clean_list(data.get("key_points"), 6),
        "why_it_matters": _clean_str(data.get("why_it_matters"), 600),
        "implications": _clean_list(data.get("implications"), 3),
        "importance": round(_clamp(data.get("importance_score", data.get("importance")), 0.0, 10.0), 1),
        "relevance": round(_clamp(data.get("relevance_score", data.get("relevance")), 0.0, 10.0), 1),
        "content_type": content_type,
        "keywords": keywords,
        "model": config.LLM_MODEL,
    }


def build_structured_summary(analysis: dict[str, Any]) -> str:
    """Turn a normalized LLM analysis into the reader's markdown-ish brief."""
    lines: list[str] = ["## TL;DR", analysis["summary"]]
    points = analysis.get("key_points") or []
    if points:
        lines.append("## Key points")
        lines.extend(f"- {point}" for point in points)
    if analysis.get("why_it_matters"):
        lines.append("## Why it matters")
        lines.append(analysis["why_it_matters"])
    implications = analysis.get("implications") or []
    if implications:
        lines.append("## Implications")
        lines.extend(f"- {item}" for item in implications)
    return "\n".join(lines)


class LLMProvider:
    """Minimal provider interface; swap implementations without changing callers."""

    name = "base"

    def analyze_article(self, *, title: str, source: str, text: str,
                        published_at: str | None = None) -> dict[str, Any] | None:
        raise NotImplementedError


STORY_PROMPT = """You compare several news reports about the same event.

Use only what the supplied reports say. Do not invent facts, numbers, quotes or events.
Write in plain, simple English that anyone can follow.

Return valid JSON with exactly these fields:
{
  "headline": "One plain sentence saying what happened.",
  "agree": ["3-4 short facts that several of the reports share"],
  "differ": ["0-3 short points where the reports differ in emphasis, figures or tone; name the outlet"]
}"""


def normalize_story_brief(data: dict[str, Any]) -> dict[str, Any] | None:
    """Validate raw model JSON for a story brief; None when it is unusable."""
    if not isinstance(data, dict):
        return None
    agree = _clean_list(data.get("agree"), 5, 320)
    if not agree:
        return None
    return {
        "headline": _clean_str(data.get("headline"), 220),
        "agree": agree,
        "differ": _clean_list(data.get("differ"), 4, 320),
    }


class OpenAICompatibleProvider(LLMProvider):
    """Provider for OpenAI and any server exposing /chat/completions."""

    name = "openai-compatible"

    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 model: str | None = None, timeout: float | None = None):
        self.base_url = (base_url or config.LLM_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else config.LLM_API_KEY
        self.model = model or config.LLM_MODEL
        self.timeout = timeout or config.LLM_TIMEOUT

    def _payload(self, *, title: str, source: str, text: str,
                 published_at: str | None, json_mode: bool) -> dict[str, Any]:
        article = (
            f"Title: {title}\nPublisher: {source}\n"
            f"Publication date: {published_at or 'unknown'}\n\n"
            f"Article text:\n{text[: config.LLM_MAX_INPUT_CHARS]}"
        )
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": article},
            ],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def analyze_article(self, *, title: str, source: str, text: str,
                        published_at: str | None = None) -> dict[str, Any] | None:
        if not text or len(text) < 120:
            return None

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        def _post(json_mode: bool) -> httpx.Response:
            return httpx.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=self._payload(title=title, source=source, text=text,
                                   published_at=published_at, json_mode=json_mode),
                timeout=self.timeout,
            )

        try:
            resp = _post(True)
            if resp.status_code == 400:
                # Some local servers reject response_format; retry plain.
                resp = _post(False)
            resp.raise_for_status()
            body = resp.json()
            content = body["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001 - never let the LLM break enrichment
            logger.warning("[llm] analysis failed: %s", exc)
            return None

        raw = _extract_json(content)
        analysis = normalize_analysis(raw) if raw else None
        if analysis is None:
            logger.warning("[llm] unusable response (first 120 chars): %.120s", content)
        return analysis


def _complete_json(provider: "OpenAICompatibleProvider", system: str, user: str) -> str | None:
    """One chat completion that is asked for JSON; returns the message text or None."""
    headers = {"Content-Type": "application/json"}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"

    def _post(json_mode: bool) -> httpx.Response:
        payload: dict[str, Any] = {
            "model": provider.model, "temperature": 0.2,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        return httpx.post(f"{provider.base_url}/chat/completions", headers=headers, json=payload,
                          timeout=provider.timeout)

    try:
        resp = _post(True)
        if resp.status_code == 400:
            resp = _post(False)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001 - a failed brief must never break the page
        logger.warning("[llm] story brief failed: %s", exc)
        return None


def story_brief(*, title: str, reports: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Ask the configured model to compare a story's reports. None when LLM is off or unusable."""
    provider = get_provider()
    if provider is None or not reports:
        return None
    body = "\n\n".join(
        f"[{r['source']}] {r['title']}\n{r['text'][: config.LLM_MAX_INPUT_CHARS // max(len(reports), 1)]}"
        for r in reports
    )
    content = _complete_json(provider, STORY_PROMPT, f"Story: {title}\n\nReports:\n{body}")
    raw = _extract_json(content or "")
    brief = normalize_story_brief(raw) if raw else None
    if brief is None:
        logger.warning("[llm] unusable story brief (first 120 chars): %.120s", content or "")
        return None
    brief["model"] = provider.model
    return brief


def get_provider() -> LLMProvider | None:
    """Return the configured provider, or None when LLM analysis is off."""
    if not available():
        return None
    return OpenAICompatibleProvider()


def analyze_article(*, title: str, source: str, text: str,
                    published_at: str | None = None) -> dict[str, Any] | None:
    """Convenience wrapper: analyze with the configured provider, or return None."""
    provider = get_provider()
    if provider is None:
        return None
    return provider.analyze_article(title=title, source=source, text=text,
                                    published_at=published_at)
