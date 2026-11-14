// Small formatting helpers for dates, links, topics, keywords and outlet colours.

/** Relative time such as '5m ago', or a date once it is a week old. */
export function timeAgo(iso: string | null): string {
  if (!iso) return 'unknown date'
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}

/** Hostname without "www." so users can see where a story really lives. */
export function domainOf(url: string): string {
  try {
    // Drop a leading "www." so "www.bbc.co.uk" reads as "bbc.co.uk".
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return ''
  }
}

/** Emoji shown for each topic. */
export const TOPIC_EMOJI: Record<string, string> = {
  Technology: '💻',
  Business: '📈',
  Science: '🔬',
  Politics: '🏛️',
  Health: '🩺',
  World: '🌍',
  General: '📰',
}

/** Split a comma-separated keyword string into a trimmed list, up to `max`. */
export function keywordList(keywords: string | null, max = Infinity): string[] {
  return (keywords ?? '')
    .split(',')
    .map((k) => k.trim())
    .filter(Boolean)
    .slice(0, max)
}

/** Stable accent hue for a source name, so each outlet keeps its own colour. */
export function sourceHue(name: string): number {
  let h = 0
  // Simple string hash (multiplier 31) folded onto the 360 degrees of the colour wheel.
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 360
  return h
}
