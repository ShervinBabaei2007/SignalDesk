/* ============================================================
   SignalDesk dashboard logic
   ============================================================ */

const $ = (id) => document.getElementById(id);
const API = "/api";

const state = {
  filters: { search: "", source: "", topic: "", sentiment: "", order: "newest" },
  debounceTimer: null,
  offset: 0,
  limit: 25,
  total: 0,
  loaded: [],
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
  loadDigest();

  // populate topic filter
  const topicSelect = $("f-topic");
  const currentTopic = topicSelect.value;
  topicSelect.innerHTML = '<option value="">All topics</option>' +
    Object.keys(s.topic_breakdown).sort().map((t) => `<option value="${t}">${t}</option>`).join("");
  topicSelect.value = currentTopic;
}

/* ---------- Daily Brief ---------- */

async function loadDigest() {
  try {
    const d = await api("/digest");
    $("digest-headline").textContent = d.headline;
    const groups = [
      ["▲ Most positive", d.top_positive, "digest-pos", "var(--pos)"],
      ["▼ Most negative", d.top_negative, "digest-neg", "var(--neg)"],
    ];
    $("digest-extremes").innerHTML = groups
      .filter(([, items]) => items && items.length)
      .map(([label, items, cls, color]) => `
        <div>
          <div class="digest-group-title" style="color:${color}">${label}</div>
          ${items.map((item) => `
            <a class="digest-item ${cls}" href="/#/article/${item.id}" data-id="${item.id}">
              <span class="digest-score">${item.sentiment >= 0 ? "+" : ""}${item.sentiment.toFixed(2)}</span>
              ${escapeHtml(item.title.length > 60 ? item.title.slice(0, 60) + "…" : item.title)}
            </a>`).join("")}
        </div>`)
      .join("");
    $("digest-extremes").querySelectorAll(".digest-item").forEach((el) =>
      el.addEventListener("click", (e) => { e.preventDefault(); location.hash = `#/article/${el.dataset.id}`; }));
  } catch (err) {
    $("digest-headline").textContent = "Brief unavailable";
  }
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
    svg.innerHTML = `<text x="50%" y="55%" text-anchor="middle" style="fill:var(--text-dim)" font-size="10">collecting data…</text>`;
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
    <line x1="0" y1="${h - pad - ((0 - min) / range) * (h - pad * 2)}" x2="${w}" y2="${h - pad - ((0 - min) / range) * (h - pad * 2)}" style="stroke:var(--border)" stroke-dasharray="3 4" stroke-width="1"/>
    <path d="${area}" fill="${color}" opacity="0.1"/>
    <path d="${line}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${coords.at(-1)[0]}" cy="${coords.at(-1)[1]}" r="3" fill="${color}"/>`;
}

/* ---------- Articles ---------- */

async function loadArticles(append = false) {
  if (!append) {
    $("empty-state").classList.add("hidden");
    state.offset = 0;
    showSkeletons();
  } else {
    $("loading").classList.remove("hidden");
  }
  const params = new URLSearchParams({ limit: state.limit, offset: state.offset, order: state.filters.order });
  for (const [key, value] of Object.entries(state.filters)) {
    if (key !== "order" && value && value.trim()) params.set(key, value.trim());
  }
  try {
    const page = await api(`/articles?${params}`);
    state.total = page.total;
    if (append) state.loaded.push(...page.items);
    else state.loaded = page.items;
    $("result-count").textContent = `${page.total} article${page.total === 1 ? "" : "s"}`;
    renderArticles(state.loaded);
    $("load-more").classList.toggle("hidden", state.loaded.length >= state.total);
  } catch (err) {
    toast(`Failed to load articles: ${err.message}`);
  } finally {
    $("loading").classList.add("hidden");
  }
}

function showSkeletons(count = 6) {
  const list = $("articles");
  list.innerHTML = "";
  for (let i = 0; i < count; i++) {
    const sk = document.createElement("div");
    sk.className = "skeleton-card";
    sk.innerHTML = `
      <div class="skeleton sk-icon"></div>
      <div class="skeleton-main">
        <div class="skeleton sk-line" style="width:42%"></div>
        <div class="skeleton sk-line" style="width:88%"></div>
        <div class="skeleton sk-line" style="width:72%"></div>
        <div class="skeleton sk-line sk-short" style="width:34%"></div>
      </div>`;
    list.appendChild(sk);
  }
}

const SENTIMENT_GLYPH = { positive: "▲", neutral: "●", negative: "▼" };

function badge(label) {
  return `<span class="badge badge-${label}">${SENTIMENT_GLYPH[label] || "●"} ${label}</span>`;
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
    card.dataset.id = a.id;
    card.style.cursor = "pointer";
    card.style.animationDelay = `${Math.min(state.loaded.indexOf(a) % state.limit, 8) * 40}ms`;
    const cleanSummary = a.summary_deep || a.summary;
    const keywords = (a.keywords || "").split(",").map((k) => k.trim()).filter(Boolean).slice(0, 4);
    card.innerHTML = `
      <div class="article-topic" title="${a.topic}">${TOPIC_EMOJI[a.topic] || "📰"}</div>
      <div class="article-main">
        <div class="article-meta">
          <span class="article-source">${escapeHtml(a.source)}</span>
          <span>·</span><span>${timeAgo(a.published_at)}</span>
          ${badge(a.sentiment_label)}
          <span class="sentiment-score">${a.sentiment >= 0 ? "+" : ""}${a.sentiment.toFixed(2)}</span>
          ${a.summary_deep ? '<span class="deep-tag" title="Summary generated from the full article page">✨ deep</span>' : ""}
        </div>
        <h3 class="article-title"><a href="/#/article/${a.id}">${escapeHtml(a.title)}</a></h3>
        ${cleanSummary ? `<p class="article-summary">${escapeHtml(cleanSummary)}</p>` : ""}
        <div class="article-footer">
          <div class="article-chips">
            <span class="chip">${TOPIC_EMOJI[a.topic] || "📰"} ${a.topic}</span>
            ${keywords.map((k) => `<span class="chip">${escapeHtml(k)}</span>`).join("")}
          </div>
          <div class="card-actions">
            <button class="card-action" data-summary="${a.id}" title="Straight-to-the-point summary">📄 Summary</button>
            ${a.is_seed
              ? '<span class="card-action demo-tag" title="Demo article — placeholder content, no external page">🌱 Demo</span>'
              : `<a class="card-action" href="${escapeHtml(a.url)}" target="_blank" rel="noopener" title="Open the original website" onclick="event.stopPropagation()">↗ Visit</a>`}
          </div>
        </div>
      </div>`;
    card.addEventListener("click", () => { location.hash = `#/article/${a.id}`; });
    card.querySelector("[data-summary]").addEventListener("click", (e) => {
      e.stopPropagation();
      location.hash = `#/article/${a.id}`;
    });
    list.appendChild(card);
  }
}

/* ---------- Routing ---------- */

function route() {
  const match = location.hash.match(/^#\/article\/(\d+)$/);
  if (match) {
    showArticle(+match[1]);
  } else {
    // Dashboard view: reader hidden, feed restored as-is
    $("reader-view").classList.add("hidden");
    $("dashboard-view").classList.remove("hidden");
  }
}

/* ---------- Article reader page ---------- */

function slugify(text) {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

/* Render the structured summary ("## Heading" / "- bullet" lines) as a
   skimmable hierarchy of section cards, plus a chip TOC for fast navigation. */
function renderStructured(markdown, container, toc) {
  container.innerHTML = "";
  if (toc) toc.innerHTML = "";
  const lines = (markdown || "").split("\n");
  let section = null;
  const sections = [];
  const flush = () => {
    if (!section) return;
    const box = document.createElement("div");
    box.className = "reader-section";
    box.id = `sec-${slugify(section.title)}`;
    const h = document.createElement("h4");
    h.className = "reader-section-title";
    h.textContent = section.title;
    box.appendChild(h);
    if (section.bullets.length) {
      const ul = document.createElement("ul");
      ul.className = "reader-section-list";
      for (const b of section.bullets) {
        const li = document.createElement("li");
        li.textContent = b;
        ul.appendChild(li);
      }
      box.appendChild(ul);
    }
    for (const para of section.paras) {
      const p = document.createElement("p");
      p.textContent = para;
      box.appendChild(p);
    }
    container.appendChild(box);
    sections.push({ title: section.title, id: box.id });
  };
  for (const line of lines) {
    if (line.startsWith("## ")) {
      flush();
      section = { title: line.slice(3).trim(), bullets: [], paras: [] };
    } else if (!line.trim()) {
      continue;
    } else if (line.startsWith("- ")) {
      if (section) section.bullets.push(line.slice(2).trim());
    } else if (section) {
      section.paras.push(line.trim());
    }
  }
  flush();

  // TOC chips: click to jump to a section
  if (toc && sections.length > 1) {
    toc.classList.remove("hidden");
    for (const s of sections) {
      const chip = document.createElement("button");
      chip.className = "toc-chip";
      chip.textContent = s.title;
      chip.addEventListener("click", () => {
        document.getElementById(s.id)?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      toc.appendChild(chip);
    }
  } else if (toc) {
    toc.classList.add("hidden");
  }
}

async function showArticle(id) {
  $("dashboard-view").classList.add("hidden");
  $("reader-view").classList.remove("hidden");
  window.scrollTo(0, 0);

  $("reader-title").textContent = "Loading…";
  $("reader-summary").textContent = "";
  $("reader-body").innerHTML = "";
  $("reader-generate").classList.add("hidden");
  $("reader-link").removeAttribute("href");

  let a;
  try {
    a = await api(`/articles/${id}`);
  } catch (err) {
    $("reader-title").textContent = "Article not found";
    toast(err.message);
    return;
  }

  $("reader-meta").innerHTML = `
    <span class="article-topic-emoji">${TOPIC_EMOJI[a.topic] || "📰"}</span>
    <span class="article-source">${escapeHtml(a.source)}</span>
    <span>·</span><span>${timeAgo(a.published_at)}</span>
    ${badge(a.sentiment_label)}
    ${a.summary_deep ? '<span class="deep-tag" title="Summary generated from the full article page">✨ deep</span>' : ""}`;
  $("reader-title").textContent = a.title;
  const keywords = (a.keywords || "").split(",").map((k) => k.trim()).filter(Boolean);
  $("reader-keywords").innerHTML = keywords.map((k) => `<span class="chip">${escapeHtml(k)}</span>`).join("");
  $("reader-score").textContent = `${a.sentiment >= 0 ? "+" : ""}${a.sentiment.toFixed(2)}`;
  $("reader-gauge").style.left = `${((a.sentiment + 1) / 2) * 90 + 5}%`;

  const link = $("reader-link");
  if (a.is_seed) {
    link.classList.add("hidden");
  } else {
    link.classList.remove("hidden");
    link.href = a.url;
  }

  const genBtn = $("reader-generate");
  const updateSummary = (article) => {
    $("reader-summary").textContent = article.summary_deep || article.summary || "No summary available yet.";
    if (article.summary_deep) {
      genBtn.classList.add("hidden");
    } else {
      genBtn.classList.remove("hidden");
      genBtn.disabled = false;
      genBtn.textContent = "✨ Generate clean summary";
    }
  };
  updateSummary(a);

  // Body: structured skimmable sections (the brief IS the article content)
  const renderBody = (article) => {
    if (article.summary_structured) {
      // The summary box above already shows the TL;DR — don't repeat it
      let md = article.summary_structured;
      if (article.summary_deep) md = md.replace(/^## TL;DR\n[\s\S]*?(?=## )/, "");
      renderStructured(md, $("reader-body"), $("reader-toc"));
    } else {
      $("reader-toc").classList.add("hidden");
      $("reader-body").innerHTML =
        '<p class="reader-note">No brief generated yet — use the button above to read the article.</p>';
    }
  };
  renderBody(a);

  if (!a.full_text && !a.summary_structured && !a.summary_deep) {
    // First visit, never enriched: pull the page automatically so the
    // reader shows real content from the article's URL
    genBtn.disabled = true;
    genBtn.classList.remove("hidden");
    genBtn.textContent = "⏳ Reading the article…";
    try {
      const updated = await api(`/articles/${id}/summarize`, { method: "POST" });
      updateSummary(updated);
      renderBody(updated);
      loadArticles(true);
    } catch (err) {
      toast(err.message);
      updateSummary(a);
    }
  }

  genBtn.onclick = async () => {
    genBtn.disabled = true;
    genBtn.textContent = "⏳ Reading the article…";
    try {
      const updated = await api(`/articles/${id}/summarize`, { method: "POST" });
      updateSummary(updated);
      renderBody(updated);
      loadArticles(true);
    } catch (err) {
      toast(err.message);
      genBtn.disabled = false;
      genBtn.textContent = "✨ Generate clean summary";
    }
  };
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
    const status = feed.last_status
      ? `<span class="feed-status ${feed.last_status.startsWith("ok") ? "feed-ok" : "feed-err"}">${escapeHtml(feed.last_status)}${feed.last_fetched_at ? " · " + timeAgo(feed.last_fetched_at) : ""}</span>`
      : "";
    const li = document.createElement("li");
    li.innerHTML = `
      <div><span class="feed-name">${escapeHtml(feed.name)}</span>
      <span class="feed-url">${escapeHtml(feed.url)}</span>${status}</div>
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

/* ---------- Settings (theme + compact mode) ---------- */

const SETTINGS_KEY = "signaldesk-settings";

function loadSettings() {
  try { return JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}"); }
  catch { return {}; }
}

/* Saved settings with URL params (?theme=light&compact=1) taking precedence */
function effectiveSettings() {
  const s = loadSettings();
  const q = new URLSearchParams(location.search);
  if (q.get("theme")) s.theme = q.get("theme");
  if (q.has("compact")) s.compact = q.get("compact") !== "0";
  return s;
}

function saveSettings(patch) {
  const s = { ...loadSettings(), ...patch };
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
  return s;
}

function applySettingsToUI(s) {
  const theme = s.theme || "dark";
  const compact = !!s.compact;
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.compact = compact ? "on" : "off";
  for (const btn of document.querySelectorAll("[data-theme-choice]")) {
    btn.setAttribute("aria-checked", String(btn.dataset.themeChoice === theme));
  }
  $("compact-toggle").setAttribute("aria-checked", String(compact));
}

function initSettings() {
  applySettingsToUI(effectiveSettings());

  $("settings-btn").addEventListener("click", () => $("settings-modal").showModal());
  $("settings-close").addEventListener("click", () => $("settings-modal").close());
  // ?settings=1 opens the menu directly (shareable/demo/testing)
  if (new URLSearchParams(location.search).has("settings")) $("settings-modal").showModal();

  for (const btn of document.querySelectorAll("[data-theme-choice]")) {
    btn.addEventListener("click", () => {
      applySettingsToUI(saveSettings({ theme: btn.dataset.themeChoice }));
      toast(`Theme switched to ${btn.dataset.themeChoice} mode`);
    });
  }

  $("compact-toggle").addEventListener("click", () => {
    const s = saveSettings({ compact: !loadSettings().compact });
    applySettingsToUI(s);
    // fewer articles per page when compact
    state.limit = s.compact ? 10 : 25;
    loadArticles();
    toast(s.compact ? "Compact mode on — calmer, less on screen" : "Compact mode off — full dashboard restored");
  });
}

/* ---------- Wire up ---------- */

document.addEventListener("DOMContentLoaded", () => {
  // settings first so compact mode affects the initial article load
  initSettings();
  if (effectiveSettings().compact) state.limit = 10;

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

  $("load-more").addEventListener("click", () => {
    state.offset += state.limit;
    loadArticles(true);
  });

  // hash routing: #/article/{id} → reader page, everything else → dashboard
  window.addEventListener("hashchange", route);
  route();

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
  $("f-order").addEventListener("change", (e) => { state.filters.order = e.target.value; loadArticles(); });

  // auto-refresh stats every 60s
  setInterval(loadStats, 60000);
});
