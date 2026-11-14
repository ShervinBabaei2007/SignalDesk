// Display-time cleanup of article summaries.
//
// Summaries are extracted from real web pages, so page furniture sometimes rides along: share-button rows,
// "FULL STORY" teasers, stock-photo credits, "Published On" stamps. The server now strips these for new
// articles (backend/app/analysis.py); this removes them from summaries that are already stored.

const SHARE = '(?:Facebook|Twitter|Pinterest|LinkedIn|WhatsApp|Reddit|Email|Print|Share)'

/** Patterns that are never part of the story. Each needs to be specific enough not to eat real prose. */
const FURNITURE: RegExp[] = [
  new RegExp(`\\b${SHARE}(?:\\s+${SHARE}){2,}\\b`, 'gi'), // a row of three or more share buttons (pages vary the casing)
  /\bFULL\s+STORY\b/g,
  /\bCredit:\s*(?:Shutterstock|Getty\s+Images|Alamy|iStock|Adobe\s+Stock)\b/gi,
  /\bPublished\s+On\s+\d{1,2}\s+\w{3}\s+\d{4}(?:\s+\d{1,2}\s+\w{3}\s+\d{4})?(?:\s+Save)?/g,
  /\bRecommended\s+Stories\s+list\s+of\s+\d+\s+items(?:\s+list\s+\d+\s+of\s+\d+)?/gi,
]

/** A summary without scraped page furniture, with whitespace tidied. */
export function cleanSummary(text: string): string {
  let out = text
  for (const pattern of FURNITURE) out = out.replace(pattern, ' ')
  return out.replace(/\s{2,}/g, ' ').replace(/^[\s.,;:–-]+/, '').trim()
}
