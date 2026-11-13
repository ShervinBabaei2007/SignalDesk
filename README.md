# ⚡ SignalDesk

> **AI-powered news intelligence, on autopilot.**
> SignalDesk pulls news from RSS feeds around the web, deduplicates it, scores sentiment, classifies topics, and surfaces it all in a real-time intelligence dashboard.

![Status](https://img.shields.io/badge/status-MVP-brightgreen) ![Python](https://img.shields.io/badge/python-3.12%2B-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-latest-teal) ![Tests](https://img.shields.io/badge/tests-18%20passing-brightgreen) ![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## What it does

```mermaid
graph LR
    A["📡 RSS Feeds<br/>(BBC, The Verge, TechCrunch, HN…)"] --> B["📥 Ingestion Pipeline<br/>fetch → dedupe (unique URL)"]
    B --> C["🧠 Analysis Engine<br/>sentiment · topic · summary · keywords"]
    C --> D[("🗄️ Database<br/>SQLite / PostgreSQL")]
    D --> E["📊 Dashboard<br/>KPIs · trend chart · filters"]
    E --> F["🔍 Signal Feed<br/>search · filter · explore"]
```

Every article that enters the system is automatically:

- **Scored for sentiment** in `[-1.0, +1.0]` with negation and intensifier handling
- **Classified** into one of 6 topics (Technology, Business, Science, Politics, Health, World)
- **Summarized** with an extractive summary
- **Deduplicated** by URL, so re-running ingestion never creates duplicates

## Highlights

| | |
|---|---|
| 📡 **Live RSS ingestion** | Pull from any RSS feed with one click — 110 real articles in under 2 seconds |
| 🧠 **Zero-dependency NLP** | Deterministic lexicon-based analysis that works offline; clean interface for swapping in an LLM later |
| 📊 **Intelligence dashboard** | Dark-mode UI with KPI cards, 7-day sentiment trend chart, topic breakdown, and instant filters |
| 🗄️ **Zero-config persistence** | SQLite by default, PostgreSQL with one environment variable |
| 🌱 **Demo seeding** | Auto-seeds 28 realistic articles on first boot — the dashboard never looks empty |
| ✅ **Tested** | 18 pytest tests covering the analysis engine and the full API surface |
| 🐳 **One-container deploy** | `docker compose up --build` and you're done |

## Quick start

```bash
git clone https://github.com/<you>/SignalDesk.git
cd SignalDesk

# 1. Install dependencies
python -m venv .venv
.venv\Scripts\pip install -r backend/requirements.txt   # Windows
# source .venv/bin/activate && pip install -r backend/requirements.txt  # macOS/Linux

# 2. Run the server
cd backend
..\.venv\Scripts\python -m uvicorn app.main:app --reload

# 3. Open the dashboard
start http://localhost:8000
```

That's it — the database creates and seeds itself on first boot. No config files, no API keys, no external services.

### Docker

```bash
docker compose up --build
# → http://localhost:8000
```

## The dashboard

Open **http://localhost:8000** to get:

- **KPI row** — total articles, sources, last-24h volume, average sentiment, sentiment split
- **7-day sentiment trend** — SVG sparkline of daily average sentiment
- **Topic breakdown** — clickable topic distribution bars
- **Signal Feed** — every article with sentiment badge, score, topic chip, and summary
- **Filters** — live search, source, topic, and sentiment filters
- **📡 Feeds manager** — add/remove RSS feeds from the UI
- **⬇ Ingest Feeds** — one-click pipeline run with a live results report

Interactive API docs live at **http://localhost:8000/docs** (Swagger UI).

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Service health + row counts |
| `GET` | `/api/stats` | KPIs, sentiment split, topic breakdown, 7-day trend |
| `GET` | `/api/articles` | Search/filter/paginate articles |
| `GET` | `/api/articles/{id}` | Single article |
| `GET` | `/api/feeds` | List configured feeds |
| `POST` | `/api/feeds` | Add a feed (`{"name", "url"}`) |
| `DELETE` | `/api/feeds/{id}` | Remove a feed |
| `POST` | `/api/ingest` | Fetch all active feeds → dedupe → analyze → store |

## Project structure

```
SignalDesk/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app, routes, static serving
│   │   ├── database.py      # Engine + sessions (SQLite → Postgres switchable)
│   │   ├── models.py        # SQLAlchemy models (Article, Feed)
│   │   ├── schemas.py       # Pydantic request/response schemas
│   │   ├── analysis.py      # Sentiment · topics · summary · keywords
│   │   ├── ingestion.py     # RSS fetch → dedupe → analyze → store
│   │   └── seed_data.py     # Demo data auto-seeded on first boot
│   └── tests/               # pytest: analysis unit tests + API integration
├── frontend/                # Zero-build dashboard (vanilla HTML/CSS/JS)
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── Dockerfile
├── docker-compose.yml
└── pytest.ini
```

## Design decisions

- **Deterministic NLP over LLM-by-default.** The lexicon-based analyzer runs offline, is instant, and behaves identically on every demo run — ideal for a showcase. The `analyze()` interface is a single function, so dropping in an OpenAI/Anthropic-backed implementation is a one-file change.
- **Deduplication at the storage layer.** URLs are unique-indexed; ingestion upserts are idempotent, so the pipeline can run on a schedule without supervision.
- **No build step for the frontend.** Vanilla JS keeps the project instantly runnable and reviewable — the entire UI is three readable files.
- **SQLite-first.** The default needs zero infrastructure; `DATABASE_URL=postgresql://…` is the only change required for Postgres.

## Testing

```bash
.venv\Scripts\python -m pytest -q
# 18 passed
```

## Roadmap

- [ ] LLM-backed analysis backend (plug into `analysis.analyze`)
- [ ] Scheduled background ingestion (APScheduler)
- [ ] Keyword/entity highlighting in article summaries
- [ ] Email/Slack digest of daily signals
- [ ] Auth + multi-user workspaces

## License

MIT — see [MIT-LICENSE.txt](MIT-LICENSE.txt).
