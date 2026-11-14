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
  /** The outlet's source-signals score, when there is enough data. */
  reliability: number | null
  reliability_label: string | null
}

/** One factual claim and how the outlets treat it. */
export interface Claim {
  text: string
  status: 'agreed' | 'disputed' | 'single'
  outlets: string[]
  /** Each outlet's figure, for disputed claims. */
  values: Record<string, string> | null
}

/** The claim-level comparison of a story. */
export interface Claims {
  kind: 'ai' | 'auto'
  items: Claim[]
}

/** One day of an event's coverage. */
export interface TimelineDay {
  date: string
  reports: number
  outlets: number
  new_outlets: string[]
  avg_sentiment: number | null
  headline: string | null
}

/** How coverage of an event developed day by day. */
export interface StoryTimeline {
  event_id: number | null
  first_seen: string | null
  last_seen: string | null
  days_active: number
  reports: number
  outlets: number
  peak_reports: number
  sentiment_shift: number
  first_reported_by: string | null
  days: TimelineDay[]
}

/** One part of a source's signals score, with its working. */
export interface ScoreComponent {
  key: string
  label: string
  /** Null when there is not enough evidence yet. */
  points: number | null
  max: number
  detail: string
}

/** An evidence-based profile of one outlet (not an editorial rating). */
export interface SourceProfile {
  source: string
  articles: number
  score: number | null
  label: string
  breakdown: ScoreComponent[]
  corroboration_rate: number
  first_report_rate: number | null
  corrections: { notices: number; rate: number; policy: boolean }
}

/** All outlet profiles with the standing disclaimer. */
export interface SourceList {
  note: string
  window_days: number
  items: SourceProfile[]
}

/** How one feed behaved in the window. */
export interface FeedHealth {
  feed: string
  runs: number
  failures: number
  failure_rate: number
  p95_latency_ms: number
  articles_added: number
  last_error: string | null
  last_ok_at: string | null
}

/** Pipeline health for the shared data. */
export interface Observability {
  window_hours: number
  runs: {
    total: number
    failed: number
    success_rate: number | null
    p50_ms: number
    p95_ms: number
    last_at: string | null
    last_ok_at: string | null
    minutes_since_ok: number | null
  }
  throughput: { added: number; per_hour: number; series: { at: string; added: number }[] }
  feeds: { ok: number; failing: number; items: FeedHealth[] }
  extraction: { page: number; fallback: number; success_rate: number | null }
  backlog: { awaiting_enrichment: number; awaiting_embedding: number | null }
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
  claims: Claims
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
  /** When the event was first covered, if it is tracked. */
  first_seen?: string | null
  days_active?: number
}

/** The daily brief. */
export interface Digest {
  generated_at: string
  articles_last_24h: number
  avg_sentiment: number
  topic_breakdown: Record<string, number>
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
  /** Build an error from the server's message and its HTTP status code. */
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
  // The server signs demo tokens as "demo.<expiry>.<signature>".
  return token.startsWith('demo.')
}

/** True when a stored token is a private-workspace token. */
export function isWorkspaceToken(token: string): boolean {
  // The server signs workspace tokens as "ws.<id>.<signature>".
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
  // The owner's real token already allows everything the tour does, so keep it.
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
  // Resume a stored workspace, and never swap the owner's token for a weaker one.
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
    // FastAPI validation errors (422) arrive as a list of { loc, msg } entries.
    if (Array.isArray(detail)) {
      detail = detail.map((d: { loc?: string[]; msg: string }) => `${(d.loc ?? []).join('.')}: ${d.msg}`).join('; ')
    } else if (typeof detail === 'object') {
      detail = JSON.stringify(detail)
    }
    throw new ApiError(String(detail), res.status)
  }
  // 204 No Content has no body to parse.
  return (res.status === 204 ? null : await res.json()) as T
}

/** How many top stories count as "hot". Mirrors HOT_STORIES in backend/app/story_index.py. */
export const HOT_STORIES = 8

/** Build the query string for the feed endpoints from filters, paging and saved ids. */
export function feedParams(filters: Filters, offset: number, limit: number, ids?: string): URLSearchParams {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset), order: filters.order })
  // Send every non-blank filter except order (already set) and saved (sent as ids instead).
  for (const [key, value] of Object.entries(filters)) {
    if (key !== 'order' && key !== 'saved' && value.trim()) params.set(key, value.trim())
  }
  if (ids !== undefined) params.set('ids', ids) // "0" matches nothing: an empty saved list shows an empty feed
  return params
}

/** One method per backend endpoint. */
export const api = {
  /** Server status, counts and enabled features. */
  health: () => request<Health>('/health'),
  /** Totals and sentiment figures for the dashboard. */
  stats: () => request<Stats>('/stats'),
  /** The daily brief of the most positive and negative articles. */
  digest: () => request<Digest>('/digest'),
  /** The stories most outlets are covering right now. */
  trending: (limit = HOT_STORIES) => request<TrendingStory[]>(`/trending?limit=${limit}`),
  /** Email the daily brief through the configured delivery channels. */
  sendDigest: () => request<{ sent: string[] }>('/digest/send', { method: 'POST' }),
  /** One page of the flat feed, one entry per report. */
  articles: (filters: Filters, offset: number, limit: number, ids?: string) =>
    request<ArticlePage>(`/articles?${feedParams(filters, offset, limit, ids)}`),
  /** One page of the grouped feed, one entry per event. */
  stories: (filters: Filters, offset: number, limit: number, ids?: string) =>
    request<StoryPage>(`/stories?${feedParams(filters, offset, limit, ids)}`),
  /** A story with its reports, outlet comparison, brief and claims. */
  story: (id: number) => request<StoryDetail>(`/stories/${id}`),
  /** Regenerate a story's brief and return the updated story. */
  refreshBrief: (id: number) => request<StoryDetail>(`/stories/${id}/brief`, { method: 'POST' }),
  /** How a story's coverage developed day by day. */
  timeline: (id: number) => request<StoryTimeline>(`/stories/${id}/timeline`),
  /** Evidence-based profiles of every outlet. */
  sources: () => request<SourceList>('/sources'),
  /** Pipeline health over the last `hours`. */
  observability: (hours = 24) => request<Observability>(`/observability?hours=${hours}`),
  /** An article with its full text and analysis. */
  article: (id: number) => request<ArticleDetail>(`/articles/${id}`),
  /** Ask the server to (re)write an article's summary. */
  summarize: (id: number) => request<ArticleDetail>(`/articles/${id}/summarize`, { method: 'POST' }),
  /** The RSS feeds visible to this visitor. */
  feeds: () => request<Feed[]>('/feeds'),
  /** Subscribe to a new RSS feed. */
  addFeed: (name: string, url: string) =>
    request<Feed>('/feeds', { method: 'POST', body: JSON.stringify({ name, url }) }),
  /** Add the server's starter set of feeds. */
  addDefaultFeeds: () => request<Feed[]>('/feeds/defaults', { method: 'POST' }),
  /** Unsubscribe from a feed. */
  deleteFeed: (id: number) => request<null>(`/feeds/${id}`, { method: 'DELETE' }),
  /** Delete everything in the visitor's workspace. */
  resetWorkspace: () => request<null>('/workspace', { method: 'DELETE' }),
  /** The watchlist rules with their match counts. */
  watches: () => request<Watch[]>('/watches'),
  /** Create a watchlist rule. */
  addWatch: (term: string, topic: string | null, minOutlets: number) =>
    request<Watch>('/watches', { method: 'POST', body: JSON.stringify({ term, topic, min_outlets: minOutlets }) }),
  /** Pause or resume a watchlist rule. */
  setWatchActive: (id: number, isActive: boolean) =>
    request<Watch>(`/watches/${id}`, { method: 'PATCH', body: JSON.stringify({ is_active: isActive }) }),
  /** Remove a watchlist rule. */
  deleteWatch: (id: number) => request<null>(`/watches/${id}`, { method: 'DELETE' }),
  /** Fetch the feeds now and report what was added. */
  ingest: () => request<IngestResult>('/ingest', { method: 'POST' }),
}
