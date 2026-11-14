import { describe, expect, it } from 'vitest'
import { basePath, isLocked, modeFromPath, prefixRedirect, withBase } from '@/lib/mode'

describe('mode paths', () => {
  it('reads the mode from the first segment only', () => {
    expect(modeFromPath('/demo')).toBe('demo')
    expect(modeFromPath('/workspace/story/3')).toBe('workspace')
    expect(modeFromPath('/article/5')).toBeNull()
    expect(modeFromPath('/demonstration')).toBeNull()
  })

  it('prefixes in-app paths with the current mode', () => {
    expect(withBase('/demo/article/1', '/story/2')).toBe('/demo/story/2')
    expect(withBase('/workspace', '/')).toBe('/workspace')
    expect(withBase('/article/1', '/')).toBe('/')
    expect(basePath('/')).toBe('')
  })

  it('moves demo and workspace visitors from unprefixed paths to their prefix', () => {
    expect(prefixRedirect('/', 'workspace')).toBe('/workspace')
    expect(prefixRedirect('/article/5', 'demo')).toBe('/demo/article/5')
    expect(prefixRedirect('/article/5', 'owner')).toBeNull()
    expect(prefixRedirect('/', 'browse')).toBeNull()
  })
})

describe('isLocked', () => {
  it('locks every listed feature in the demo only', () => {
    for (const f of ['feeds', 'watchlist', 'brief', 'export'] as const) {
      expect(isLocked('demo', f)).toBe(true)
      expect(isLocked('workspace', f)).toBe(false)
      expect(isLocked('owner', f)).toBe(false)
    }
  })
})
