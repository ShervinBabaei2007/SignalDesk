/* Plain-English reading of a sentiment score (-1 … +1).
   Sentiment counts the positive and negative *words* in an article; it does
   not judge whether the news itself is good or bad. Single source of truth for
   every label, blurb and threshold shown in the UI. */

export type Tone = 'positive' | 'neutral' | 'negative'

/** Mirrors backend/app/sentiment.py. Change both together. */
export const POSITIVE_ABOVE = 0.15
export const NEGATIVE_BELOW = -0.15

export interface SentimentLevel {
  label: string
  tone: Tone
  range: string
  blurb: string
}

export const SENTIMENT_LEVELS: SentimentLevel[] = [
  { label: 'Very positive', tone: 'positive', range: '+0.50 to +1', blurb: 'Mostly positive words, like “win”, “record” or “breakthrough”.' },
  { label: 'Positive', tone: 'positive', range: '+0.15 to +0.50', blurb: 'More positive words than negative ones.' },
  { label: 'Neutral', tone: 'neutral', range: '−0.15 to +0.15', blurb: 'A balanced mix of positive and negative words, or plain factual wording.' },
  { label: 'Negative', tone: 'negative', range: '−0.50 to −0.15', blurb: 'More negative words than positive ones.' },
  { label: 'Very negative', tone: 'negative', range: '−1 to −0.50', blurb: 'Mostly negative words, like “crisis”, “collapse” or “outage”.' },
]

export function formatScore(score: number): string {
  return `${score >= 0 ? '+' : '−'}${Math.abs(score).toFixed(2)}`
}

export function describeSentiment(score: number): SentimentLevel & { score: string } {
  const L = SENTIMENT_LEVELS
  const level =
    score >= 0.5 ? L[0] : score > POSITIVE_ABOVE ? L[1] : score >= NEGATIVE_BELOW ? L[2] : score > -0.5 ? L[3] : L[4]
  return { ...level, score: formatScore(score) }
}

/** Wording for an average over many articles ("Mostly positive", …). */
export function describeAverage(avg: number): string {
  if (avg >= 0.5) return 'Very positive'
  if (avg > POSITIVE_ABOVE) return 'Mostly positive'
  if (avg >= NEGATIVE_BELOW) return 'Mixed or neutral'
  if (avg > -0.5) return 'Mostly negative'
  return 'Very negative'
}

/** 0–100 position of a score on the −1…+1 scale (for gauges). */
export function scalePosition(score: number): number {
  return Math.min(100, Math.max(0, ((score + 1) / 2) * 100))
}
