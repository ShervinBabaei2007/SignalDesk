// Tests for the API client's requests and error handling.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, EMPTY_FILTERS, HOT_STORIES, api, getToken, isDemoToken, startDemo } from '@/lib/api'

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
