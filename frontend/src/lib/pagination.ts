/** Page numbers to show: always the first and last page and the neighbours of the
 *  current one, with 'gap' where pages are skipped. e.g. 1 … 4 5 6 … 20 */
export type PageItem = number | 'gap'

/** Compute the page numbers to show, with gaps for skipped ranges. */
export function pageWindow(current: number, total: number, siblings = 1): PageItem[] {
  if (total <= 1) return total === 1 ? [1] : []
  const keep = new Set<number>([1, total])
  for (let p = current - siblings; p <= current + siblings; p++) {
    if (p >= 1 && p <= total) keep.add(p)
  }
  const pages = [...keep].sort((a, b) => a - b)
  const out: PageItem[] = []
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
