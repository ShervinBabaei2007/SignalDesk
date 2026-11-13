/* Parses the backend's structured brief ("## Heading" / "- bullet" lines)
   into sections the reader renders as skimmable cards. */

export interface Section {
  id: string
  title: string
  bullets: string[]
  paras: string[]
}

export function slugify(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

export function parseStructured(markdown: string | null, dropTldr: boolean): Section[] {
  let md = markdown ?? ''
  // The summary box already shows the TL;DR, so don't repeat it.
  if (dropTldr) md = md.replace(/^## TL;DR\n[\s\S]*?(?=## )/, '')
  const sections: Section[] = []
  let current: Section | null = null
  for (const raw of md.split('\n')) {
    const line = raw.trimEnd()
    if (line.startsWith('## ')) {
      const title = line.slice(3).trim()
      current = { id: `sec-${slugify(title)}`, title, bullets: [], paras: [] }
      sections.push(current)
    } else if (!line.trim() || !current) {
      continue
    } else if (line.startsWith('- ')) {
      current.bullets.push(line.slice(2).trim())
    } else {
      current.paras.push(line.trim())
    }
  }
  return sections
}
