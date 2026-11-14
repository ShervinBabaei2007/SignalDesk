// Tests for the API client's requests and error handling.
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError, EMPTY_FILTERS, HOT_STORIES, api, authMessage, getAuthStatus, getToken, isDemoToken, sessionMode, setToken,
  startDemo, startWorkspace,
} from '@/lib/api'

/** Replace fetch with a stub returning the given status and body. */
function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn(async () => new Response(status === 204 ? null : JSON.stringify(body), { status }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** The URL the stubbed fetch was last called with. */
function requestedUrl(fetchMock: ReturnType<typeof stubFetch>): string {
  return (fetchMock.mock.calls[0] as unknown as [string])[0]
}

afterEach(() => vi.unstubAllGlobals())

describe('api over a fake fetch', () => {
  it('sends filters, paging and saved ids as the query string', async () => {
    const fetchMock = stubFetch(200, { items: [], total: 0, article_total: 0, offset: 40, limit: 20 })
    await api.stories({ ...EMPTY_FILTERS, search: ' oil ', topic: 'Business', saved: '1', order: 'info' }, 40, 20, '0')
    const url = new URL(requestedUrl(fetchMock), 'http://x')
    expect(url.pathname).toBe('/api/stories')
    expect(Object.fromEntries(url.searchParams)).toEqual({
      limit: '20', offset: '40', order: 'info', search: 'oil', topic: 'Business', ids: '0',
    })
  })

  it('asks for the hot stories by default', async () => {
    const fetchMock = stubFetch(200, [])
    await api.trending()
    expect(requestedUrl(fetchMock)).toBe(`/api/trending?limit=${HOT_STORIES}`)
  })

  it('turns an error body into an ApiError with the status', async () => {
    stubFetch(429, { detail: 'An ingestion just ran' })
    await expect(api.ingest()).rejects.toMatchObject({ status: 429, message: 'An ingestion just ran' })
    await expect(api.ingest()).rejects.toBeInstanceOf(ApiError)
  })

  it('joins validation errors into one readable message', async () => {
    stubFetch(422, { detail: [{ loc: ['body', 'term'], msg: 'field required' }, { loc: ['body', 'min_outlets'], msg: 'too small' }] })
    await expect(api.addWatch('', null, 0)).rejects.toMatchObject({
      status: 422, message: 'body.term: field required; body.min_outlets: too small',
    })
  })

  it('reads a 204 as null', async () => {
    stubFetch(204, null)
    await expect(api.deleteWatch(1)).resolves.toBeNull()
  })
})

describe('isDemoToken', () => {
  it('tells demo tokens apart from the real API token', () => {
    expect(isDemoToken('demo.1700000000.abc')).toBe(true)
    expect(isDemoToken('a-real-token')).toBe(false)
    expect(isDemoToken('')).toBe(false)
  })
})

describe('startDemo', () => {
  it('stores the demo token handed out by the server', async () => {
    const store: Record<string, string> = {}
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => void (store[k] = v),
      removeItem: (k: string) => void delete store[k],
    })
    stubFetch(200, { token: 'demo.1.abc' })
    expect(await startDemo()).toBe(true)
    expect(getToken()).toBe('demo.1.abc')
  })

  it('reports false when demo mode is off on the server', async () => {
    vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => {}, removeItem: () => {} })
    stubFetch(404, { detail: 'Demo mode is not enabled' })
    expect(await startDemo()).toBe(false)
  })
})

/** Back localStorage with a plain object so tokens can be stored and read in tests. */
function stubStorage(initial: Record<string, string> = {}) {
  const store = { ...initial }
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => void (store[k] = v),
    removeItem: (k: string) => void delete store[k],
  })
}

describe('sessionMode', () => {
  it('tells a workspace, the demo, the owner and a plain visitor apart', () => {
    expect(sessionMode('ws.abc.sig')).toBe('workspace')
    expect(sessionMode('demo.1.sig')).toBe('demo')
    expect(sessionMode('a-real-token')).toBe('owner')
    expect(sessionMode('')).toBe('browse')
  })

  it('explains a refused action according to how the visitor is using the app', () => {
    expect(authMessage('ws.abc.sig')).toMatch(/site owner/)
    expect(authMessage('demo.1.sig')).toMatch(/workspace/)
    expect(authMessage('')).toMatch(/workspace/)
    expect(authMessage('real')).toMatch(/API token/)
  })
})

describe('startWorkspace', () => {
  it('stores the workspace token the server issues', async () => {
    stubStorage()
    const fetchMock = stubFetch(201, { token: 'ws.abc.sig' })
    expect(await startWorkspace()).toEqual({ ok: true })
    expect(getToken()).toBe('ws.abc.sig')
    expect((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].method).toBe('POST')
  })

  it('resumes the workspace already stored instead of creating another', async () => {
    stubStorage({ 'signaldesk-api-token': 'ws.mine.sig' })
    const fetchMock = stubFetch(201, { token: 'ws.other.sig' })
    expect(await startWorkspace()).toEqual({ ok: true })
    expect(getToken()).toBe('ws.mine.sig')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('never replaces the owner token', async () => {
    stubStorage({ 'signaldesk-api-token': 'owner-secret' })
    stubFetch(201, { token: 'ws.x.sig' })
    await startWorkspace()
    expect(getToken()).toBe('owner-secret')
  })

  it('passes on the server message when it refuses (rate limit, workspaces off)', async () => {
    stubStorage()
    stubFetch(429, { detail: 'Too many workspaces created from this network; try again later' })
    expect(await startWorkspace()).toEqual({ ok: false, message: 'Too many workspaces created from this network; try again later' })
    expect(getToken()).toBe('')
  })

  it('reports an unreachable server', async () => {
    stubStorage()
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline') }))
    expect((await startWorkspace()).ok).toBe(false)
  })
})

describe('switching between the demo and a workspace', () => {
  it('drops a workspace token when the visitor takes the demo tour, but keeps the owner token', async () => {
    stubStorage({ 'signaldesk-api-token': 'ws.mine.sig' })
    stubFetch(200, { token: 'demo.1.abc' })
    expect(await startDemo()).toBe(true)
    expect(getToken()).toBe('demo.1.abc')

    setToken('owner-secret')
    expect(await startDemo()).toBe(true)
    expect(getToken()).toBe('owner-secret')
  })
})

describe('getAuthStatus', () => {
  it('reads which entry modes the server offers', async () => {
    stubFetch(200, { required: true, demo: true, workspaces: true, workspace_ttl_days: 7 })
    expect(await getAuthStatus()).toMatchObject({ workspaces: true, workspace_ttl_days: 7 })
  })

  it('assumes nothing is offered when the server cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline') }))
    expect(await getAuthStatus()).toEqual({ required: false, demo: false, workspaces: false })
  })
})
