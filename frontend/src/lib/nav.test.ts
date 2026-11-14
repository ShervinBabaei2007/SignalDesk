import { beforeEach, describe, expect, it, vi } from 'vitest'
import { enterDashboard, leaveDashboard, navigateTo, registerRouter } from '@/lib/nav'

const navigate = vi.fn()

/** Pretend the visitor is at `pathname` and register a stub router that records navigation. */
function at(pathname: string) {
  navigate.mockClear()
  registerRouter({ state: { location: { pathname } }, navigate } as never)
}

describe('navigation from inside a mode', () => {
  beforeEach(() => at('/workspace/story/2'))

  it('keeps in-app links inside the current mode', () => {
    navigateTo('/article/5')
    expect(navigate).toHaveBeenCalledWith('/workspace/article/5')
  })

  it('leaves the workspace for the real /welcome page, not /workspace/welcome', () => {
    leaveDashboard()
    expect(navigate).toHaveBeenCalledWith('/welcome')
  })

  it('enters the dashboard at the unprefixed root', () => {
    enterDashboard()
    expect(navigate).toHaveBeenCalledWith('/')
  })
})
