import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, EMPTY_FILTERS, HOT_STORIES, api } from '@/lib/api'

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn(async () => new Response(status === 204 ? null : JSON.stringify(body), { status }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => vi.unstubAllGlobals())

describe('api over a fake fetch', () => {
  it('sends filters, paging and saved ids as the query string', async () => {
    const fetchMock = stubFetch(200, { items: [], total: 0, article_total: 0, offset: 40, limit: 20 })
    await api.stories({ ...EMPTY_FILTERS, search: ' oil ', topic: 'Business', saved: '1', order: 'info' }, 40, 20, '0')
    const url = new URL((fetchMock.mock.calls[0] as unknown as [string])[0], 'http://x')
    expect(url.pathname).toBe('/api/stories')
    expect(Object.fromEntries(url.searchParams)).toEqual({
      limit: '20', offset: '40', order: 'info', search: 'oil', topic: 'Business', ids: '0',
    })
  })

  it('asks for the hot stories by default', async () => {
    const fetchMock = stubFetch(200, [])
    await api.trending()
    expect((fetchMock.mock.calls[0] as unknown as [string])[0]).toBe(`/api/trending?limit=${HOT_STORIES}`)
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
