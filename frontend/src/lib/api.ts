/* Typed client for the SignalDesk REST API (unchanged by the React rebuild). */

export const TOKEN_KEY = 'signaldesk-api-token'

export interface Article {
  id: number
  title: string
  url: string
  source: string
  summary: string | null
  summary_deep: string | null
  keywords: string | null
  image_url: string | null
  why_it_matters: string | null
  importance: number | null
  relevance: number | null
  content_type: string | null
  analysis_source: string | null
  topic: string
  sentiment: number
  sentiment_label: 'positive' | 'neutral' | 'negative'
  published_at: string | null
  ingested_at: string
  cluster_id: number | null
  cluster_size: number
  cluster_sources: string[]
  is_seed: boolean
}

export interface RelatedArticle {
  id: number
  title: string
  source: string
  url: string
  published_at: string | null
  sentiment: number
  summary: string | null
  summary_deep: string | null
}

export interface ArticleDetail extends Article {
  related: RelatedArticle[]
  full_text: string | null
  summary_structured: string | null
  enriched_at: string | null
  analysis_model: string | null
}

export interface ArticlePage {
  total: number
  items: Article[]
  offset: number
  limit: number
}

export interface Stats {
  total_articles: number
  total_sources: number
  avg_sentiment: number
  ingested_last_24h: number
  positive: number
  neutral: number
  negative: number
  topic_breakdown: Record<string, number>
  sentiment_7d: { date: string; avg_sentiment: number; count?: number }[]
}

export interface DigestItem {
  id: number
  title: string
  source: string
  sentiment: number
  topic: string
  url: string
}

export interface TrendingStory {
  cluster_id: number
  article_id: number
  title: string
  reports: number
  outlets: number
  sources: string[]
  topic: string
  avg_sentiment: number
  latest_at: string
}

export interface Digest {
  headline: string
  top_positive: DigestItem[]
  top_negative: DigestItem[]
}

export interface Feed {
  id: number
  name: string
  url: string
  is_active: boolean
  last_fetched_at: string | null
  last_status: string | null
}

export interface IngestResult {
  added: number
  fetched: number
  skipped: number
  duration_seconds: number
  enrich_queued: number
}

export interface Health {
  status: string
  articles: number
  feeds: number
}

export interface Filters {
  search: string
  source: string
  topic: string
  sentiment: string
  cluster: string
  order: string
}

export const EMPTY_FILTERS: Filters = {
  search: '',
  source: '',
  topic: '',
  sentiment: '',
  cluster: '',
  order: 'newest',
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export function getToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? ''
  } catch {
    return ''
  }
}

export function setToken(token: string) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage unavailable (private mode): the token just won't persist */
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken()
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'X-API-Key': token } : {}),
      ...init.headers,
    },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    let detail: unknown = body.detail ?? `${res.status} ${res.statusText}`
    if (Array.isArray(detail)) {
      detail = detail.map((d: { loc?: string[]; msg: string }) => `${(d.loc ?? []).join('.')}: ${d.msg}`).join('; ')
    } else if (typeof detail === 'object') {
      detail = JSON.stringify(detail)
    }
    throw new ApiError(String(detail), res.status)
  }
  return (res.status === 204 ? null : await res.json()) as T
}

export const api = {
  health: () => request<Health>('/health'),
  stats: () => request<Stats>('/stats'),
  digest: () => request<Digest>('/digest'),
  trending: (limit = 5) => request<TrendingStory[]>(`/trending?limit=${limit}`),
  sendDigest: () => request<{ sent: string[] }>('/digest/send', { method: 'POST' }),
  articles: (filters: Filters, offset: number, limit: number) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset), order: filters.order })
    for (const [key, value] of Object.entries(filters)) {
      if (key !== 'order' && value.trim()) params.set(key, value.trim())
    }
    return request<ArticlePage>(`/articles?${params}`)
  },
  article: (id: number) => request<ArticleDetail>(`/articles/${id}`),
  summarize: (id: number) => request<ArticleDetail>(`/articles/${id}/summarize`, { method: 'POST' }),
  feeds: () => request<Feed[]>('/feeds'),
  addFeed: (name: string, url: string) =>
    request<Feed>('/feeds', { method: 'POST', body: JSON.stringify({ name, url }) }),
  addDefaultFeeds: () => request<Feed[]>('/feeds/defaults', { method: 'POST' }),
  deleteFeed: (id: number) => request<null>(`/feeds/${id}`, { method: 'DELETE' }),
  ingest: () => request<IngestResult>('/ingest', { method: 'POST' }),
}
