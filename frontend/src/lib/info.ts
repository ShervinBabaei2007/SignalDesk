/* Plain-English reading of the 0–100 information score (see backend/app/quality.py).
   It measures how much real information a report carries — article depth, figures,
   quotes and analysis — and says nothing about which outlet wrote it. */

export interface InfoLevel {
  label: string
  /** Tailwind classes for the bar and text colour. */
  bar: string
  text: string
}

export function infoLevel(score: number | null | undefined): InfoLevel & { value: number } {
  const value = Math.round(score ?? 0)
  if (value >= 75) return { value, label: 'Very detailed', bar: 'bg-link', text: 'text-link' }
  if (value >= 50) return { value, label: 'Detailed', bar: 'bg-link/70', text: 'text-link' }
  if (value >= 25) return { value, label: 'Brief', bar: 'bg-muted-foreground/60', text: 'text-muted-foreground' }
  return { value, label: 'Thin', bar: 'bg-muted-foreground/40', text: 'text-muted-foreground' }
}

export const INFO_EXPLAINER =
  'How much real information this report carries: article length, figures, quotes and analysis. It does not depend on which outlet wrote it.'
