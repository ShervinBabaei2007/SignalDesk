/** One entry of the pager: a page number, or 'gap' where pages are skipped. */
export type PageItem = number | 'gap'

/** Page numbers to show: the first, the last and the current page's neighbours, e.g. 1 … 4 5 6 … 20. */
export function pageWindow(current: number, total: number, siblings = 1): PageItem[] {
  if (total <= 1) return total === 1 ? [1] : []
  const keep = new Set<number>([1, total])
  // Keep the current page and `siblings` pages either side of it that exist.
  for (let p = current - siblings; p <= current + siblings; p++) {
    if (p >= 1 && p <= total) keep.add(p)
  }
  const pages = [...keep].sort((a, b) => a - b)
  const out: PageItem[] = []
  // Emit each kept page, bridging the jump from the previous one with a page or a gap.
  pages.forEach((p, i) => {
    const prev = pages[i - 1]
    if (prev !== undefined) {
      if (p - prev === 2) out.push(prev + 1) // a single skipped page is cheaper to show than "…"
      else if (p - prev > 2) out.push('gap')
    }
    out.push(p)
  })
  return out
}
