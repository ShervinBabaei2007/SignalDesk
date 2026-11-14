/* Pure helpers for the reader's personal library (saved and read articles).
   Kept free of React and localStorage so the rules are easy to test. */

/** Most read articles remembered, so the stored list cannot grow without bound. */
export const MAX_READ = 2000

/** Parse a stored JSON list of ids, ignoring anything that isn't a positive integer. */
export function parseIds(raw: string | null): number[] {
  if (!raw) return []
  try {
    const value = JSON.parse(raw)
    if (!Array.isArray(value)) return []
    // Keep only positive integers and drop duplicates, preserving the stored order.
    return [...new Set(value.filter((v): v is number => Number.isInteger(v) && v > 0))]
  } catch {
    return []
  }
}

/** Add `id` to the front (newest first) or remove it if present. */
export function toggleId(ids: number[], id: number): number[] {
  return ids.includes(id) ? ids.filter((i) => i !== id) : [id, ...ids]
}

/** Remember `id` as read, newest first, keeping the list bounded. */
export function addRead(ids: number[], id: number): number[] {
  // Already the newest: return the same array so callers can skip a needless save.
  if (ids[0] === id) return ids
  return [id, ...ids.filter((i) => i !== id)].slice(0, MAX_READ)
}
