import { describe, expect, it } from 'vitest'
import { parseState, progress, STEPS } from '@/lib/onboarding'

describe('onboarding', () => {
  it('treats missing or malformed storage as a first visit', () => {
    expect(parseState(null)).toEqual({ welcomed: false, dismissed: false, done: [] })
    expect(parseState('not json')).toEqual({ welcomed: false, dismissed: false, done: [] })
  })

  it('keeps only string step ids', () => {
    expect(parseState('{"welcomed":true,"done":["feed",3,null]}').done).toEqual(['feed'])
  })

  it('counts only steps that belong to the mode, once each', () => {
    expect(progress('workspace', ['feed', 'feed', 'story', 'bogus'])).toEqual({ done: 2, total: STEPS.workspace.length })
    expect(progress('demo', [])).toEqual({ done: 0, total: STEPS.demo.length })
  })

  it('gives every step a unique id within its mode', () => {
    for (const steps of Object.values(STEPS)) expect(new Set(steps.map((s) => s.id)).size).toBe(steps.length)
  })
})
