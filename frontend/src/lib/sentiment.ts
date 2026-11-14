/* Plain-English reading of a sentiment score (-1 … +1).
   Sentiment counts the positive and negative *words* in an article; it does
   not judge whether the news itself is good or bad. Single source of truth for
   every label, blurb and threshold shown in the UI. */

/** Sentiment bucket used for colours and icons. */
export type Tone = 'positive' | 'neutral' | 'negative'

/** Neutral band edges, mirroring backend/app/sentiment.py (change both together). */
export const POSITIVE_ABOVE = 0.15
export const NEGATIVE_BELOW = -0.15
/** 'Very' positive / negative start here (frontend wording only). */
export const STRONG_ABOVE = 0.5
export const STRONG_BELOW = -0.5

/** A named sentiment band with its range and plain-English explanation. */
export interface SentimentLevel {
  label: string
  tone: Tone
  range: string
  blurb: string
}

/** The sentiment bands from most to least positive. */
export const SENTIMENT_LEVELS: SentimentLevel[] = [
  { label: 'Very positive', tone: 'positive', range: `${formatScore(STRONG_ABOVE)} to +1`, blurb: 'Mostly positive words, like “win”, “record” or “breakthrough”.' },
  { label: 'Positive', tone: 'positive', range: `${formatScore(POSITIVE_ABOVE)} to ${formatScore(STRONG_ABOVE)}`, blurb: 'More positive words than negative ones.' },
  { label: 'Neutral', tone: 'neutral', range: `${formatScore(NEGATIVE_BELOW)} to ${formatScore(POSITIVE_ABOVE)}`, blurb: 'A balanced mix of positive and negative words, or plain factual wording.' },
  { label: 'Negative', tone: 'negative', range: `${formatScore(STRONG_BELOW)} to ${formatScore(NEGATIVE_BELOW)}`, blurb: 'More negative words than positive ones.' },
  { label: 'Very negative', tone: 'negative', range: `−1 to ${formatScore(STRONG_BELOW)}`, blurb: 'Mostly negative words, like “crisis”, “collapse” or “outage”.' },
]

/** Format a score with an explicit sign and two decimals. */
export function formatScore(score: number): string {
  return `${score >= 0 ? '+' : '−'}${Math.abs(score).toFixed(2)}`
}

/** Index of the band a score falls in. */
function levelIndex(score: number): number {
  if (score >= STRONG_ABOVE) return 0
  if (score > POSITIVE_ABOVE) return 1
  if (score >= NEGATIVE_BELOW) return 2
  if (score > STRONG_BELOW) return 3
  return 4
}

/** Describe a score as a band plus its formatted value. */
export function describeSentiment(score: number): SentimentLevel & { score: string } {
  return { ...SENTIMENT_LEVELS[levelIndex(score)], score: formatScore(score) }
}

/** Wording for an average over many articles ("Mostly positive", …). */
export function describeAverage(avg: number): string {
  if (avg >= STRONG_ABOVE) return 'Very positive'
  if (avg > POSITIVE_ABOVE) return 'Mostly positive'
  if (avg >= NEGATIVE_BELOW) return 'Mixed or neutral'
  if (avg > STRONG_BELOW) return 'Mostly negative'
  return 'Very negative'
}

/** 0–100 position of a score on the −1…+1 scale (for gauges). */
export function scalePosition(score: number): number {
  return Math.min(100, Math.max(0, ((score + 1) / 2) * 100))
}
