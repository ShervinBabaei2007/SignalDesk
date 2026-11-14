// Small pure helpers for the claims, timeline, sources and pipeline views.
import type { Tone } from '@/lib/sentiment'

/** Score bands, mirroring the server's labels (Strong / Mixed / Limited signals) in backend/app/reliability.py. */
export const STRONG_FROM = 70
export const MIXED_FROM = 45

/** Colour tone for a source-signals score (null when there is not enough data). */
export function reliabilityTone(score: number | null): Tone | null {
  if (score === null) return null
  if (score >= STRONG_FROM) return 'positive'
  if (score >= MIXED_FROM) return 'neutral'
  return 'negative'
}

/** Bar heights in percent for a series, scaled to its peak; any non-zero value stays visible. */
export function barHeights(values: number[]): number[] {
  const peak = Math.max(...values, 0)
  if (peak === 0) return values.map(() => 0)
  return values.map((v) => (v === 0 ? 0 : Math.max(Math.round((v / peak) * 100), 6)))
}

/** A duration in milliseconds as short readable text: 850 ms, 3.2 s, 1m 05s. */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)} s`
  return `${Math.floor(s / 60)}m ${String(Math.round(s % 60)).padStart(2, '0')}s`
}

/** A fraction as a whole percentage, or a dash when there is no data. */
export function percent(value: number | null): string {
  return value === null ? '–' : `${Math.round(value * 100)}%`
}

/** "12 min ago", "3 h ago": how long since the last good run, from minutes. */
export function minutesAgo(minutes: number | null): string {
  if (minutes === null) return 'never'
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  return hours < 48 ? `${hours} h ago` : `${Math.round(hours / 24)} d ago`
}

/** The pipeline is stale when no cycle has succeeded for this many minutes (the scheduler runs every 15). */
export const STALE_AFTER_MINUTES = 60

/** One-letter weekday for a YYYY-MM-DD date, in UTC so every reader sees the same day. */
export function dayInitial(date: string): string {
  return new Date(`${date}T00:00:00Z`).toLocaleDateString(undefined, { weekday: 'narrow', timeZone: 'UTC' })
}

/** "Mon 5" style label for a YYYY-MM-DD date. */
export function dayLabel(date: string): string {
  return new Date(`${date}T00:00:00Z`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', timeZone: 'UTC' })
}

/** One bucket of the throughput series: a UTC hour (YYYY-MM-DDTHH:00) or day (YYYY-MM-DD) and how many articles arrived. */
export interface Bucket {
  at: string
  added: number
}

/** The throughput series on a complete time axis. The server only reports periods that had a run, so a quiet
 *  hour would otherwise be missing and one data point would stretch across the whole chart. Hourly up to two
 *  days, daily beyond (matching the server's bucketing). */
export function fillSeries(series: Bucket[], hours: number, now: Date = new Date()): Bucket[] {
  const daily = hours > 48
  const step = daily ? 86_400_000 : 3_600_000
  const count = daily ? Math.ceil(hours / 24) : hours
  const byKey = new Map(series.map((b) => [b.at, b.added]))
  const out: Bucket[] = []
  for (let i = count - 1; i >= 0; i--) {
    const iso = new Date(now.getTime() - i * step).toISOString()
    const at = daily ? iso.slice(0, 10) : `${iso.slice(0, 13)}:00`
    out.push({ at, added: byKey.get(at) ?? 0 })
  }
  return out
}
