/* Typed client for the SignalDesk REST API (unchanged by the React rebuild). */

/** localStorage key for the API token. */
export const TOKEN_KEY = 'signaldesk-api-token'

/** An article as listed in the feed. */
export interface Article {
  id: number
  title: string
  url: string
  source: string
  summary: string | null
  summary_deep: string | null
  keywords: string | null
  image_url: string | null
  info_score: number | null
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

/** A compact report shown as another take on the same story. */
export interface RelatedArticle {
  id: number
  title: string
  source: string
  url: string
  published_at: string | null
  sentiment: number
  info_score: number | null
  summary: string | null
  summary_deep: string | null
}

/** A report shown under its story's lead, best-informed first. */
export interface ReportBrief {
  id: number
  title: string
  source: string
  url: string
  published_at: string | null
  sentiment: number
  info_score: number | null
  summary: string | null
  image_url: string | null
}

/** One event: the best-informed report leads, the other outlets' reports follow. */
export interface Story {
  key: string
  cluster_id: number | null
  lead: Article
  others: ReportBrief[]
  report_count: number
  outlets: number
  sources: string[]
  best_score: number | null
  watch_matches: string[]
}

/** A page of stories. */
export interface StoryPage {
  total: number
  article_total: number
  items: Story[]
  offset: number
  limit: number
}

/** One outlet's standing within a story. */
export interface OutletStat {
  source: string
  report_id: number
  title: string
  info_score: number | null
  sentiment: number
  chars: number
  numbers: number
  quotes: number
  published_at: string | null
  badges: string[]
}

/** What outlets agree on and where they differ. */
export interface StoryBrief {
  kind: 'ai' | 'auto'
  headline: string
  agree: string[]
  differ: string[]
  model: string | null
  generated_at: string | null
}

/** A story with its ranked reports, outlet comparison and brief. */
export interface StoryDetail {
  cluster_id: number
  title: string
  report_count: number
  outlets: number
  avg_sentiment: number
  sentiment_spread: number
  reports: ReportBrief[]
  comparison: OutletStat[]
  brief: StoryBrief
}

/** An article with its full text and analysis. */
export interface ArticleDetail extends Article {
  related: RelatedArticle[]
  full_text: string | null
  summary_structured: string | null
  enriched_at: string | null
  analysis_model: string | null
}

/** A page of articles. */
export interface ArticlePage {
  total: number
  items: Article[]
  offset: number
  limit: number
}

/** Dashboard statistics. */
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

/** One article in the daily brief. */
export interface DigestItem {
  id: number
  title: string
  source: string
  sentiment: number
  topic: string
  url: string
}

/** A story covered by several outlets right now. */
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

/** The daily brief. */
export interface Digest {
  headline: string
  top_positive: DigestItem[]
  top_negative: DigestItem[]
}

/** An RSS feed and its health. */
export interface Feed {
  id: number
  name: string
  url: string
  is_active: boolean
  /** Part of the shared base data: visible to everyone, removable only by the owner. */
  shared: boolean
  last_fetched_at: string | null
  last_status: string | null
}

/** A watchlist rule. */
export interface Watch {
  id: number
  term: string
  topic: string | null
  min_outlets: number
  is_active: boolean
  created_at: string
  matches: number
}

/** An alert raised when a story matched a watch. */
export interface WatchAlert {
  watch_id: number
  term: string
  story_key: string
  cluster_id: number | null
  article_id: number
  title: string
  outlets: number
  reports: number
}

/** Result of an ingest run. */
export interface IngestResult {
  added: number
  fetched: number
  skipped: number
  duration_seconds: number
  enrich_queued: number
  alerts: WatchAlert[]
}

/** Server health and features. */
export interface Health {
  status: string
  articles: number
  feeds: number
  features?: { digest_delivery?: string[]; llm_analysis?: boolean; auth_required?: boolean }
}

/** The feed filters chosen in the UI. */
export interface Filters {
  search: string
  source: string
  topic: string
  sentiment: string
  cluster: string
  hot: string // '1' = only articles from the hot stories
  saved: string // '1' = only the reader's saved articles (ids come from the browser)
  order: string
}

/** Filters with nothing selected. */
export const EMPTY_FILTERS: Filters = {
  search: '',
  source: '',
  topic: '',
  sentiment: '',
  cluster: '',
  hot: '',
  saved: '',
  order: 'newest',
}

/** Error from the API carrying the HTTP status. */
export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

/** The stored API token, or an empty string. */
export function getToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? ''
  } catch {
    return ''
  }
}

/** Store or clear the API token. */
export function setToken(token: string) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage unavailable (private mode): the token just won't persist */
  }
}

/** True when a stored token is a demo token rather than the real API token. */
export function isDemoToken(token: string): boolean {
  return token.startsWith('demo.')
}

/** True when a stored token is a private-workspace token. */
export function isWorkspaceToken(token: string): boolean {
  return token.startsWith('ws.')
}

/** How the visitor is using the app: their own workspace, the demo tour, the owner, or just browsing. */
export type SessionMode = 'workspace' | 'demo' | 'owner' | 'browse'

/** The mode a stored token puts the visitor in. */
export function sessionMode(token: string): SessionMode {
  if (isWorkspaceToken(token)) return 'workspace'
  if (isDemoToken(token)) return 'demo'
  return token ? 'owner' : 'browse'
}

/** What to tell someone whose action the server refused (401), depending on how they are using the app. */
export function authMessage(token: string): string {
  switch (sessionMode(token)) {
    case 'workspace':
      return 'Only the site owner can do that'
    case 'owner':
      return 'The server rejected your API token. Check it in Settings'
    default:
      return 'Open your own workspace from the home page to make changes'
  }
}

/** What the server supports, so the landing page offers only what works. */
export interface AuthStatus {
  required: boolean
  demo: boolean
  workspaces: boolean
  /** Days before a workspace's data is deleted. */
  workspace_ttl_days?: number
}

/** Ask the server which entry modes are enabled; assumes none when it cannot be reached. */
export async function getAuthStatus(): Promise<AuthStatus> {
  try {
    const res = await fetch('/api/auth/status')
    if (res.ok) return (await res.json()) as AuthStatus
  } catch {
    /* offline or the API is down: fall through */
  }
  return { required: false, demo: false, workspaces: false }
}

/** Result of trying to enter a mode. */
export interface StartResult {
  ok: boolean
  message?: string
}

/** Start the demo tour: a short-lived token that can run ingests on the shared data (a real API token is kept). */
export async function startDemo(): Promise<boolean> {
  const current = getToken()
  if (current && sessionMode(current) === 'owner') return true
  setToken('') // leaving a workspace for the tour: the tour has its own, weaker token
  try {
    const res = await fetch('/api/demo/session', { method: 'POST' })
    if (!res.ok) return false
    const { token } = (await res.json()) as { token: string }
    if (token) setToken(token)
    return true
  } catch {
    return false
  }
}

/** Open the visitor's private workspace, resuming the one already stored in this browser. */
export async function startWorkspace(): Promise<StartResult> {
  const current = getToken()
  if (isWorkspaceToken(current) || sessionMode(current) === 'owner') return { ok: true }
  try {
    const res = await fetch('/api/workspace', { method: 'POST' })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      return { ok: false, message: body.detail ?? 'Could not start a workspace' }
    }
    const { token } = (await res.json()) as { token: string }
    setToken(token)
    return { ok: true }
  } catch {
    return { ok: false, message: 'Could not reach the server' }
  }
}

/** Call the API and return parsed JSON, turning failures into ApiError. */
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

/** How many top stories count as "hot". Mirrors HOT_STORIES in backend/app/story_index.py. */
export const HOT_STORIES = 8

/** Build the query string for the feed endpoints from filters, paging and saved ids. */
export function feedParams(filters: Filters, offset: number, limit: number, ids?: string): URLSearchParams {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset), order: filters.order })
  for (const [key, value] of Object.entries(filters)) {
    if (key !== 'order' && key !== 'saved' && value.trim()) params.set(key, value.trim())
  }
  if (ids !== undefined) params.set('ids', ids) // "0" matches nothing: an empty saved list shows an empty feed
  return params
}

/** One method per backend endpoint. */
export const api = {
  health: () => request<Health>('/health'),
  stats: () => request<Stats>('/stats'),
  digest: () => request<Digest>('/digest'),
  trending: (limit = HOT_STORIES) => request<TrendingStory[]>(`/trending?limit=${limit}`),
  sendDigest: () => request<{ sent: string[] }>('/digest/send', { method: 'POST' }),
  articles: (filters: Filters, offset: number, limit: number, ids?: string) =>
    request<ArticlePage>(`/articles?${feedParams(filters, offset, limit, ids)}`),
  stories: (filters: Filters, offset: number, limit: number, ids?: string) =>
    request<StoryPage>(`/stories?${feedParams(filters, offset, limit, ids)}`),
  story: (id: number) => request<StoryDetail>(`/stories/${id}`),
  refreshBrief: (id: number) => request<StoryDetail>(`/stories/${id}/brief`, { method: 'POST' }),
  article: (id: number) => request<ArticleDetail>(`/articles/${id}`),
  summarize: (id: number) => request<ArticleDetail>(`/articles/${id}/summarize`, { method: 'POST' }),
  feeds: () => request<Feed[]>('/feeds'),
  addFeed: (name: string, url: string) =>
    request<Feed>('/feeds', { method: 'POST', body: JSON.stringify({ name, url }) }),
  addDefaultFeeds: () => request<Feed[]>('/feeds/defaults', { method: 'POST' }),
  deleteFeed: (id: number) => request<null>(`/feeds/${id}`, { method: 'DELETE' }),
  resetWorkspace: () => request<null>('/workspace', { method: 'DELETE' }),
  watches: () => request<Watch[]>('/watches'),
  addWatch: (term: string, topic: string | null, minOutlets: number) =>
    request<Watch>('/watches', { method: 'POST', body: JSON.stringify({ term, topic, min_outlets: minOutlets }) }),
  setWatchActive: (id: number, isActive: boolean) =>
    request<Watch>(`/watches/${id}`, { method: 'PATCH', body: JSON.stringify({ is_active: isActive }) }),
  deleteWatch: (id: number) => request<null>(`/watches/${id}`, { method: 'DELETE' }),
  ingest: () => request<IngestResult>('/ingest', { method: 'POST' }),
}
