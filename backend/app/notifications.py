"""Daily brief delivery: Slack webhooks and SMTP email.

Delivery is opt-in and configuration-driven. The same builder powers the
"Send brief" button in the dashboard and the optional daily scheduler, so
there is exactly one rendering path for every channel.

Configure either (or both):

    SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
    DIGEST_EMAILS=team@example.com,me@example.com
    SMTP_HOST=smtp.example.com
    SMTP_PORT=587
    SMTP_USER=...
    SMTP_PASSWORD=...
    SMTP_FROM=signaldesk@example.com

All failures are caught and reported per channel; the API never 500s because
a webhook is down.
"""

from __future__ import annotations

import html
import logging
import smtplib
from datetime import timezone
from email.message import EmailMessage

import httpx

from . import config

logger = logging.getLogger("signaldesk.notifications")


def _fmt_item(item) -> str:
    """One plain-text line for a digest item."""
    sign = "+" if item.sentiment >= 0 else ""
    return f"{sign}{item.sentiment:.2f} · {item.title} ({item.source}) — {item.url}"


def digest_text(digest) -> str:
    """Render a digest as plain text suitable for Slack or an email body."""
    generated = digest.generated_at
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    lines = [
        f"☀️ SignalDesk Daily Brief — {generated:%b %d, %Y}",
        "",
        digest.headline,
        "",
        f"Signals: {digest.articles_last_24h} · Avg sentiment: {digest.avg_sentiment:+.2f}",
    ]

    if digest.topic_breakdown:
        topics = " · ".join(f"{name} {count}" for name, count in
                            list(digest.topic_breakdown.items())[:5])
        lines += ["", f"Topics: {topics}"]

    if digest.top_positive:
        lines += ["", "▲ Most positive"]
        lines += [f"• {_fmt_item(item)}" for item in digest.top_positive]

    if digest.top_negative:
        lines += ["", "▼ Most negative"]
        lines += [f"• {_fmt_item(item)}" for item in digest.top_negative]

    lines += ["", "— SignalDesk"]
    return "\n".join(lines)


def digest_html(digest) -> str:
    """Render a digest as a simple, email-client-friendly HTML document."""

    def esc(value) -> str:
        """HTML-escape a value."""
        return html.escape(str(value))

    def item_rows(items, color: str) -> str:
        """HTML list items for digest entries."""
        return "".join(
            f'<li style="margin:6px 0"><a href="{esc(item.url)}" '
            f'style="color:{color};text-decoration:none;font-weight:600">{esc(item.title)}</a>'
            f'<div style="color:#667085;font-size:13px">{esc(item.source)} · '
            f'{item.sentiment:+.2f}</div></li>'
            for item in items
        )

    positives = (f'<h3 style="color:#059669;margin:22px 0 6px">▲ Most positive</h3>'
                 f'<ul style="padding-left:18px;margin:0">{item_rows(digest.top_positive, "#0f172a")}</ul>'
                 if digest.top_positive else "")
    negatives = (f'<h3 style="color:#dc2626;margin:22px 0 6px">▼ Most negative</h3>'
                 f'<ul style="padding-left:18px;margin:0">{item_rows(digest.top_negative, "#0f172a")}</ul>'
                 if digest.top_negative else "")

    return f"""<!doctype html>
<html><body style="margin:0;background:#f4f6fb;font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#0f172a">
<div style="max-width:620px;margin:0 auto;padding:28px 22px">
  <div style="font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#667085">SignalDesk · Daily Brief</div>
  <h1 style="font-size:24px;line-height:1.3;margin:12px 0 8px">{esc(digest.headline)}</h1>
  <div style="color:#667085;font-size:14px">{digest.articles_last_24h} signals ·
    average sentiment {digest.avg_sentiment:+.2f}</div>
  {positives}
  {negatives}
  <p style="margin-top:26px;color:#98a2b3;font-size:12px">Generated automatically by SignalDesk.</p>
</div>
</body></html>"""


def send_slack(text: str, webhook_url: str | None = None) -> None:
    """Post a plain-text message to a Slack incoming webhook."""
    url = webhook_url or config.SLACK_WEBHOOK_URL
    if not url:
        raise ValueError("SLACK_WEBHOOK_URL is not configured")
    response = httpx.post(url, json={"text": text}, timeout=15)
    response.raise_for_status()


def send_email(subject: str, text: str, html_body: str | None = None,
               recipients: list[str] | None = None) -> None:
    """Send the digest over SMTP using STARTTLS by default."""
    recipients = recipients or config.DIGEST_EMAILS
    if not recipients:
        raise ValueError("DIGEST_EMAILS is not configured")
    if not config.SMTP_HOST:
        raise ValueError("SMTP_HOST is not configured")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.SMTP_FROM or config.SMTP_USER or "signaldesk@localhost"
    message["To"] = ", ".join(recipients)
    message.set_content(text)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as server:
        if config.SMTP_TLS:
            server.starttls()
        if config.SMTP_USER:
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(message)


def configured_channels() -> list[str]:
    """Names of the delivery channels (Slack, email) that are configured."""
    channels = []
    if config.SLACK_WEBHOOK_URL:
        channels.append("slack")
    if config.DIGEST_EMAILS and config.SMTP_HOST:
        channels.append("email")
    return channels


def _deliver(log_tag: str, subject: str, text: str, html_body: str | None = None) -> dict:
    """Send to every configured channel, collecting per-channel failures instead of raising."""
    result: dict = {"channels": configured_channels(), "sent": [], "errors": []}
    senders = []
    if config.SLACK_WEBHOOK_URL:
        senders.append(("slack", "Slack", lambda: send_slack(text)))
    if config.DIGEST_EMAILS:
        senders.append(("email", "email", lambda: send_email(subject, text, html_body)))
    for channel, name, send in senders:
        try:
            send()
            result["sent"].append(channel)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s] %s delivery failed: %s", log_tag, name, exc)
            result["errors"].append({"channel": channel, "error": str(exc)})
    return result


def deliver_alert(subject: str, text: str) -> dict:
    """Send a watchlist alert to every configured channel (same shape as deliver_digest)."""
    return _deliver("alert", subject, text)


def deliver_digest(digest) -> dict:
    """Send a digest to every configured channel.

    Returns {"channels", "sent", "errors"} so callers can report exactly what
    happened without raising for per-channel failures.
    """
    subject = f"SignalDesk Daily Brief — {digest.generated_at:%b %d, %Y}"
    return _deliver("digest", subject, digest_text(digest), digest_html(digest))
