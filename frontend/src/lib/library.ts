/* Pure helpers for the reader's personal library (saved and read articles).
   Kept free of React and localStorage so the rules are easy to test. */

export const MAX_READ = 2000 // remember at most this many read articles

/** Parse a stored JSON list of ids, ignoring anything that isn't a positive integer. */
export function parseIds(raw: string | null): number[] {
  if (!raw) return []
  try {
    const value = JSON.parse(raw)
    if (!Array.isArray(value)) return []
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
  if (ids[0] === id) return ids
  return [id, ...ids.filter((i) => i !== id)].slice(0, MAX_READ)
}
