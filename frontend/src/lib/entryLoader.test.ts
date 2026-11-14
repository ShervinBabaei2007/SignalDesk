import { describe, expect, it } from 'vitest'
import { entryLoader } from '@/lib/entryLoader'

/** The Location header of a redirect response, or null when the loader let the page render. */
function target(r: Response | null) {
  return r?.headers.get('Location') ?? null
}

describe('entryLoader', () => {
  it('sends first-time visitors at the root to the landing page', () => {
    expect(target(entryLoader('/', '', false, 'browse'))).toBe('/welcome')
  })

  it('lets returning visitors and the owner see the dashboard', () => {
    expect(entryLoader('/', '', true, 'browse')).toBeNull()
    expect(entryLoader('/article/5', '', false, 'owner')).toBeNull()
  })

  it('redirects old hash links before anything else', () => {
    expect(target(entryLoader('/', '#/article/5', false, 'browse'))).toBe('/article/5')
    expect(target(entryLoader('/', '#/story/2', true, 'browse'))).toBe('/story/2')
  })

  it('moves demo and workspace visitors under their prefix', () => {
    expect(target(entryLoader('/', '', true, 'workspace'))).toBe('/workspace')
    expect(target(entryLoader('/story/3', '', false, 'demo'))).toBe('/demo/story/3')
  })
})
