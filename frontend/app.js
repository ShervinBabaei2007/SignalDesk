/* ============================================================
   SignalDesk dashboard logic
   ============================================================ */

const $ = (id) => document.getElementById(id);
const API = "/api";

const state = {
  filters: { search: "", source: "", topic: "", sentiment: "" },
  debounceTimer: null,
};

/* ---------- Helpers ---------- */

function timeAgo(iso) {
  if (!iso) return "unknown date";
  const seconds = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

function toast(message, ms = 3200) {
  const el = $("toast");
  el.textContent = message;
  el.classList.remove("hidden");
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.add("hidden"), ms);
}

async function api(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    let detail = body.detail || `${res.status} ${res.statusText}`;
    if (Array.isArray(detail)) {
      detail = detail.map((d) => `${(d.loc || []).join(".")}: ${d.msg}`).join("; ");
    } else if (typeof detail === "object") {
      detail = JSON.stringify(detail);
    }
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

/* ---------- Stats ---------- */

async function loadStats() {
  const s = await api("/stats");

  $("stat-total").textContent = s.total_articles.toLocaleString();
  $("stat-sources").textContent = s.total_sources;
  $("stat-24h").textContent = s.ingested_last_24h;

  const avg = s.avg_sentiment;
  $("stat-sentiment").textContent = avg.toFixed(2);
  const arrow = $("stat-sentiment-arrow");
  if (avg > 0.15) { arrow.textContent = "▲"; arrow.style.color = "var(--pos)"; }
  else if (avg < -0.15) { arrow.textContent = "▼"; arrow.style.color = "var(--neg)"; }
  else { arrow.textContent = "●"; arrow.style.color = "var(--neu)"; }

  const total = Math.max(s.positive + s.neutral + s.negative, 1);
  $("bar-positive").style.width = `${(s.positive / total) * 100}%`;
  $("bar-neutral").style.width = `${(s.neutral / total) * 100}%`;
  $("bar-negative").style.width = `${(s.negative / total) * 100}%`;

  renderTopicBreakdown(s.topic_breakdown, s.total_articles);
  renderSentimentSplit(s);
  renderTrendChart(s.sentiment_7d);

  // populate topic filter
  const topicSelect = $("f-topic");
  const currentTopic = topicSelect.value;
  topicSelect.innerHTML = '<option value="">All topics</option>' +
    Object.keys(s.topic_breakdown).sort().map((t) => `<option value="${t}">${t}</option>`).join("");
  topicSelect.value = currentTopic;
}

function renderTopicBreakdown(breakdown, total) {
  const container = $("topic-breakdown");
  container.innerHTML = "";
  const entries = Object.entries(breakdown).slice(0, 7);
  const max = Math.max(...entries.map(([, n]) => n), 1);
  for (const [topic, count] of entries) {
    const row = document.createElement("div");
    row.className = "topic-row";
    row.innerHTML = `
      <span class="topic-name">${topic}</span>
      <span class="topic-bar-wrap"><span class="topic-bar" style="width:${(count / max) * 100}%"></span></span>
      <span class="topic-count">${count}</span>`;
    row.addEventListener("click", () => {
      $("f-topic").value = topic;
      state.filters.topic = topic;
      loadArticles();
    });
    container.appendChild(row);
  }
  if (!entries.length) container.innerHTML = '<span class="muted">No data yet</span>';
}

function renderSentimentSplit(s) {
  const total = s.total_articles || 1;
  const rows = [
    ["split-pos", "Positive", s.positive],
    ["split-neu", "Neutral", s.neutral],
    ["split-neg", "Negative", s.negative],
  ];
  $("sentiment-split").innerHTML = rows
    .map(([dot, label, n]) => `
      <div class="split-row">
        <span><span class="split-dot ${dot}"></span>${label}</span>
        <span class="topic-count">${n} · ${Math.round((n / total) * 100)}%</span>
      </div>`)
    .join("");
}

function renderTrendChart(points) {
  const svg = $("trend-chart");
  if (!points || points.length < 2) {
    svg.innerHTML = `<text x="50%" y="55%" text-anchor="middle" fill="#3a4257" font-size="10">collecting data…</text>`;
    return;
  }
  const vals = points.map((p) => p.avg_sentiment);
  const min = Math.min(...vals, -0.3), max = Math.max(...vals, 0.3);
  const range = max - min || 1;
  const w = 220, h = 60, pad = 4;
  const coords = vals.map((v, i) => [
    pad + (i / (vals.length - 1)) * (w - pad * 2),
    h - pad - ((v - min) / range) * (h - pad * 2),
  ]);
  const line = coords.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${line} L${coords.at(-1)[0]},${h} L${coords[0][0]},${h} Z`;
  const last = vals.at(-1);
  const color = last > 0.15 ? "var(--pos)" : last < -0.15 ? "var(--neg)" : "var(--accent)";
  svg.innerHTML = `
    <line x1="0" y1="${h - pad - ((0 - min) / range) * (h - pad * 2)}" x2="${w}" y2="${h - pad - ((0 - min) / range) * (h - pad * 2)}" stroke="#2a3247" stroke-dasharray="3 4" stroke-width="1"/>
    <path d="${area}" fill="url(#grad)" opacity="0.25"/>
    <defs><linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${color}" stop-opacity="0.5"/>
      <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
    </linearGradient></defs>
    <path d="${line}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${coords.at(-1)[0]}" cy="${coords.at(-1)[1]}" r="3" fill="${color}"/>`;
}

/* ---------- Articles ---------- */

async function loadArticles() {
  $("loading").classList.remove("hidden");
  $("empty-state").classList.add("hidden");
  const params = new URLSearchParams({ limit: 40 });
  for (const [key, value] of Object.entries(state.filters)) {
    if (value && value.trim()) params.set(key, value.trim());
  }
  try {
    const page = await api(`/articles?${params}`);
    $("result-count").textContent = `${page.total} article${page.total === 1 ? "" : "s"}`;
    renderArticles(page.items);
  } catch (err) {
    toast(`Failed to load articles: ${err.message}`);
  } finally {
    $("loading").classList.add("hidden");
  }
}

function renderArticles(items) {
  const list = $("articles");
  list.innerHTML = "";
  if (!items.length) {
    $("empty-state").classList.remove("hidden");
    return;
  }
  for (const a of items) {
    const card = document.createElement("article");
    card.className = "article-card";
    card.innerHTML = `
      <div class="article-topic" title="${a.topic}">${TOPIC_EMOJI[a.topic] || "📰"}</div>
      <div class="article-main">
        <div class="article-meta">
          <span class="article-source">${escapeHtml(a.source)}</span>
          <span>·</span><span>${timeAgo(a.published_at)}</span>
          <span class="badge badge-${a.sentiment_label}">${a.sentiment_label}</span>
          <span class="sentiment-score">${a.sentiment >= 0 ? "+" : ""}${a.sentiment.toFixed(2)}</span>
        </div>
        <h3 class="article-title"><a href="${escapeHtml(a.url)}" target="_blank" rel="noopener">${escapeHtml(a.title)}</a></h3>
        ${a.summary ? `<p class="article-summary">${escapeHtml(a.summary)}</p>` : ""}
        <div class="article-chips">
          <span class="chip">${TOPIC_EMOJI[a.topic] || "📰"} ${a.topic}</span>
        </div>
      </div>`;
    list.appendChild(card);
  }
}

const TOPIC_EMOJI = {
  Technology: "💻", Business: "📈", Science: "🔬", Politics: "🏛️",
  Health: "🩺", World: "🌍", General: "📰",
};

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

/* ---------- Ingestion ---------- */

async function runIngestion() {
  for (const btn of [ $("ingest-btn"), $("ingest-btn-2") ]) {
    btn.disabled = true;
    btn.innerHTML = `⏳ Ingesting…`;
  }
  $("ingest-result").textContent = "Fetching RSS feeds, deduplicating and analyzing…";
  try {
    const result = await api("/ingest", { method: "POST" });
    $("ingest-result").innerHTML =
      `✅ <strong>${result.added} new</strong> articles added · ` +
      `${result.fetched} fetched · ${result.skipped} duplicates skipped · ` +
      `${result.duration_seconds}s`;
    toast(`Ingestion complete — ${result.added} new articles`);
    await Promise.all([loadStats(), loadArticles()]);
  } catch (err) {
    $("ingest-result").textContent = `⚠️ ${err.message}`;
    toast(`Ingestion failed: ${err.message}`);
  } finally {
    for (const btn of [ $("ingest-btn"), $("ingest-btn-2") ]) {
      btn.disabled = false;
      btn.innerHTML = btn.id === "ingest-btn" ? `<span class="btn-icon">⬇</span> Ingest Feeds` : "Run Ingestion";
    }
  }
}

/* ---------- Feeds management ---------- */

async function loadFeeds() {
  const feeds = await api("/feeds");
  const list = $("feeds-list");
  list.innerHTML = "";
  for (const feed of feeds) {
    const li = document.createElement("li");
    li.innerHTML = `
      <div><span class="feed-name">${escapeHtml(feed.name)}</span>
      <span class="feed-url">${escapeHtml(feed.url)}</span></div>
      <button class="btn btn-ghost btn-sm btn-danger" data-id="${feed.id}" title="Remove feed">🗑</button>`;
    li.querySelector("button").addEventListener("click", async () => {
      try {
        await api(`/feeds/${feed.id}`, { method: "DELETE" });
        toast(`Removed feed "${feed.name}"`);
        loadFeeds();
      } catch (err) { toast(err.message); }
    });
    list.appendChild(li);
  }
  if (!feeds.length) list.innerHTML = '<li class="muted">No feeds configured yet.</li>';

  // populate source filter from article sources
  const sources = [...new Set((await api("/articles?limit=100")).items.map((a) => a.source))].sort();
  const select = $("f-source");
  const current = select.value;
  select.innerHTML = '<option value="">All sources</option>' +
    sources.map((s) => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join("");
  select.value = current;
}

/* ---------- Wire up ---------- */

document.addEventListener("DOMContentLoaded", () => {
  // health pill
  api("/health")
    .then((h) => {
      const pill = $("health-pill");
      pill.classList.add("pill-healthy");
      pill.innerHTML = `<span class="dot"></span> API healthy · ${h.articles} articles`;
    })
    .catch(() => { $("health-pill").innerHTML = `<span class="dot" style="background:var(--neg)"></span> API offline`; });

  loadStats();
  loadArticles();
  loadFeeds();

  $("ingest-btn").addEventListener("click", runIngestion);
  $("ingest-btn-2").addEventListener("click", runIngestion);

  $("feeds-btn").addEventListener("click", () => { loadFeeds(); $("feeds-modal").showModal(); });
  $("feeds-close").addEventListener("click", () => $("feeds-modal").close());

  $("feed-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = $("feed-name").value.trim();
    const url = $("feed-url").value.trim();
    try {
      await api("/feeds", { method: "POST", body: JSON.stringify({ name, url }) });
      $("feed-name").value = ""; $("feed-url").value = "";
      toast(`Added feed "${name}"`);
      loadFeeds();
    } catch (err) { toast(err.message); }
  });

  // filters
  $("f-search").addEventListener("input", (e) => {
    clearTimeout(state.debounceTimer);
    state.debounceTimer = setTimeout(() => {
      state.filters.search = e.target.value;
      loadArticles();
    }, 300);
  });
  $("f-source").addEventListener("change", (e) => { state.filters.source = e.target.value; loadArticles(); });
  $("f-topic").addEventListener("change", (e) => { state.filters.topic = e.target.value; loadArticles(); });
  $("f-sentiment").addEventListener("change", (e) => { state.filters.sentiment = e.target.value; loadArticles(); });

  // auto-refresh stats every 60s
  setInterval(loadStats, 60000);
});
