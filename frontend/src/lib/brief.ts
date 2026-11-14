// Plain-text version of the daily brief for copying and downloading (mirrors digest_text in backend/app/notifications.py).
import type { Digest, DigestItem } from '@/lib/api'

/** A signed two-decimal number such as "+0.12" or "-0.30". */
function signed(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}`
}

/** One text line for a brief item. */
function itemLine(item: DigestItem): string {
  return `• ${signed(item.sentiment)} · ${item.title} (${item.source}) — ${item.url}`
}

/** When the brief was generated; a timestamp with no zone is read as UTC, as the server does. */
function generatedAt(digest: Digest): Date {
  const raw = digest.generated_at
  return new Date(/(Z|[+-]\d\d:?\d\d)$/.test(raw) ? raw : `${raw}Z`)
}

/** The brief as plain text, ready to paste into an email or chat. */
export function digestText(digest: Digest): string {
  const date = generatedAt(digest).toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric', timeZone: 'UTC' })
  const lines = [
    `☀️ SignalDesk Daily Brief — ${date}`,
    '',
    digest.headline,
    '',
    `Signals: ${digest.articles_last_24h} · Avg sentiment: ${signed(digest.avg_sentiment)}`,
  ]
  // The five largest topics (the server sends them already sorted by count).
  const topics = Object.entries(digest.topic_breakdown).slice(0, 5)
  if (topics.length) lines.push('', `Topics: ${topics.map(([name, count]) => `${name} ${count}`).join(' · ')}`)
  if (digest.top_positive.length) lines.push('', '▲ Most positive', ...digest.top_positive.map(itemLine))
  if (digest.top_negative.length) lines.push('', '▼ Most negative', ...digest.top_negative.map(itemLine))
  lines.push('', '— SignalDesk')
  return lines.join('\n')
}

/** File name for a downloaded brief, such as `signaldesk-brief-2026-11-14.txt`. */
export function briefFilename(digest: Digest): string {
  return `signaldesk-brief-${generatedAt(digest).toISOString().slice(0, 10)}.txt`
}
