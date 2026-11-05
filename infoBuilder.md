# Build SignalDesk: n8n + AI + RSS News Intelligence Platform

The goal is to build an automated research platform that collects news from multiple sources, filters it to the last 7 days, removes duplicate stories, uses AI to analyze what matters, and delivers a structured daily intelligence report.

I recommend building this as a real full-stack application rather than just connecting RSS feeds to an AI node. That will make it a stronger portfolio project for backend and AI engineering roles.

What the finished application should do

1. Collect information

   Automatically retrieve articles from RSS feeds, GitHub, research publications, and official company sources.

2. Filter and clean

   Keep only recent stories, normalize metadata, and identify duplicates.

3. Analyze with AI

   Categorize stories, summarize them, rank importance, and explain why they matter.

4. Detect trends

   Identify recurring developments across multiple sources.

5. Present intelligence

   Display a searchable dashboard with daily reports, topic filters, and source links.

## 1. Choose the technology stack

I would use the following stack:

| Component     | Technology               | Responsibility                        |
| ------------- | ------------------------ | ------------------------------------- |
| Frontend      | Next.js + TypeScript     | Dashboard and user interface          |
| Styling       | Tailwind CSS + shadcn/ui | UI components                         |
| Backend       | Python + FastAPI         | Processing and business logic         |
| Automation    | n8n                      | Scheduled workflows                   |
| Database      | PostgreSQL               | Articles, users, summaries            |
| Vector search | pgvector                 | Semantic similarity and deduplication |
| Cache / queue | Redis                    | Caching and background jobs           |
| AI            | OpenAI API or local LLM  | Classification and analysis           |
| Deployment    | Docker                   | Reproducible services                 |
| CI/CD         | GitHub Actions           | Testing and deployment                |

Why this architecture?

n8n handles automation. FastAPI handles the actual application logic. PostgreSQL stores your data. The AI model analyzes the information.

Avoid putting all the business logic inside n8n Code nodes. It makes the application harder to test, maintain, and extend.

## 2. Decide what information to collect

Start with a manageable number of reliable sources. Expand later.

### Recommended news categories

[What is intelligence? | Hub](https://images.openai.com/static-rsc-4/rW27kTma18zWJ_A5w5Sr30Lh-hNl_8RqvNdAaS3fLcz_LWj6pf7-M6xOEigE3qFxGovDPU4WuqX3qszxfEJ8EiChhzDdtwKhtWdsa3L-bsrJUwhOGDj575EM3Ao_3z_r2M3S8hM7b19fzwYz5azQ7wfZZerefoXZ8tPmi8l8z78?purpose=inline)

Artificial intelligence

AI research, LLM releases, agentic systems, model benchmarks, and AI infrastructure.

[Hire a Back-end Dev Outsourced in Vietnam](https://images.openai.com/static-rsc-4/fr9S0Y78YeyPYzZ-z1GwY4ldb6zdcRDWdGnszjKxNMYSAd_fn9VRMcIgn9bHPv4DpMS_A3fTVKLGb91STPDyQwk2ZvgjkeVduog4PFv0G-xscNYTihuz1Bo9YbGfBEUCUnwFv1Roq4sUbXbAXIWwkZI-FQS0Fa5eMsw7O4ryrec?purpose=inline)

Computer science and software engineering

Programming languages, frameworks, security, databases, systems, and developer tools.

[Electronic circuit board with processor](https://images.openai.com/static-rsc-4/QOdCxlp8Tg4ShcrmqvAD7KEX2F3EMLSU9qp_48Y3LghXY9RBmeuZFyRbXmMGtVUay2VbiClfuycMTH1hOVJI4b6ZvagjTr1Vxqxm02YHbNbI1geLevk1ZAfGJsriP0o0n1q1jLEMILWTNECUK3R9DYmg9cmYae-ScMfAlgt-byjn_lSbqMxGOOY_uS6j9QP-?purpose=inline)

Technology and hardware

CPUs, GPUs, semiconductor companies, Apple, NVIDIA, AMD, Intel, and computing infrastructure.

[Gasly handed two grid penalties for impeding in Barcelona F1 qualifying](https://images.openai.com/static-rsc-4/pTZP5TMq2NNzEpB6MEYNnMh2WdZSew8uVV83cs83z7c0tQfUVwkeQMrt9n14Sb2F_7_8urlQGRbaGmVubUeUbn4Cf2ay8abfRRVEEKwA8Q7ktiRmgmdL4obiQphIWEkcUDt69D5NLfMo4kqxbsATZO1UviobGUyfrAo2F08TLCg?purpose=inline)

Formula 1

Race developments, Alpine, technical changes, driver news, and team announcements.

[wall street today: Why US stock market indexes S&P 500 and Nasdaq registered gains while Dow Jones crashed today? Full explainer on biggest gainers and losers, earnings week, oil prices, Iran tensions, Federal Reserve outlook - The Economic Times](https://images.openai.com/static-rsc-4/TyoV7u5ggDduKTsiM5rJhWicN-SlNtbVBC-h_5oRYul96DgSG2YmP3U_GYpSXN7k2A3RFWd8IpBtb_dBY8jes_Cxp91u79-d0-tyCxb1hgUiT0r4rZIZawHLWQaRWYYubGsE6m-DNt-4OCQygc3K_tT5aXEo01yfaadT2lNIsNg?purpose=inline)

Business and markets

Technology companies, earnings, market developments, and relevant economic news.

### Suggested RSS sources

| Source                | Subject                 | Feed                                              |
| --------------------- | ----------------------- | ------------------------------------------------- |
| Hacker News           | Software and technology | `https://hnrss.org/frontpage`                     |
| MIT Technology Review | Technology and AI       | `https://www.technologyreview.com/feed/`          |
| Ars Technica          | Technology              | `https://feeds.arstechnica.com/arstechnica/index` |
| The Verge             | Technology              | `https://www.theverge.com/rss/index.xml`          |
| Google Research       | AI research             | `https://research.google/blog/rss/`               |
| arXiv CS.AI           | AI research papers      | `https://export.arxiv.org/rss/cs.AI`              |
| arXiv CS.LG           | Machine learning        | `https://export.arxiv.org/rss/cs.LG`              |

Feeds can change or become unavailable, so verify them when configuring the workflow.

You can also add:

- GitHub Trending or GitHub API for trending repositories.
- Official OpenAI, Anthropic, Google DeepMind, NVIDIA, and AMD announcement pages.
- Official Formula 1 and Alpine news sources.
- Financial news feeds from reputable publishers.

Start with 5–10 feeds, not 50. You want to prove the pipeline works before increasing its volume.

## 3. Set up your development environment

I recommend developing on your Ubuntu installation.

Install:

- Docker Engine
- Docker Compose
- Git
- Python 3.12+
- Node.js LTS
- VS Code
- n8n

Check that Docker works:

```
docker --version
docker compose version
```

Create the project:

```
mkdir signaldesk
cd signaldesk

mkdir backend frontend workflows docs
```

Initialize Git:

```
git init
```

Your project structure will eventually look something like this:

```
signaldesk/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── models/
│   │   ├── services/
│   │   ├── ingestion/
│   │   ├── ai/
│   │   └── main.py
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── package.json
│
├── workflows/
│   ├── daily-ingestion.json
│   └── daily-digest.json
│
├── docs/
│   ├── architecture.md
│   └── api.md
│
├── docker-compose.yml
└── README.md
```

## 4. Set up n8n

For development, run n8n in Docker:

```
docker volume create n8n_data

docker run -it --rm \
  --name signaldesk-n8n \
  -p 5678:5678 \
  -v n8n_data:/home/node/.n8n \
  docker.n8n.io/n8nio/n8n
```

Open:

`http://localhost:5678`

Create your n8n account and configure your instance.

This is a development setup. For the finished project, use Docker Compose with persistent storage, environment variables, and a PostgreSQL database for n8n itself.

Important: n8n's own database and SignalDesk's application database should be treated as separate concerns, even if both use PostgreSQL.

## 5. Build the first n8n workflow: News ingestion

This is the first workflow you should implement.

Workflow 1 — Automated news collection

Schedule Trigger

Run every 3 hours

RSS Feed Read

Retrieve articles from configured feeds

Normalize article data

Standardize title, URL, date, source, description

Date filter

Keep only the last 7 days

HTTP Request → FastAPI

Submit normalized articles for storage and processing

### Step 5.1 — Create a workflow

In n8n:

1. Click Create Workflow.
2. Name it `SignalDesk - News Ingestion`.
3. Add a Schedule Trigger.
4. Set it to run every 3 hours.
5. Add an RSS Feed Read node.
6. Enter the URL of your first feed.
7. Execute the node and inspect the output.

The RSS node should return article information such as:

- Title
- Link
- Publication date
- Description
- Author, when available

Repeat this for your other RSS sources. You can merge their outputs before normalization.

### Step 5.2 — Normalize the data

Different publishers use different RSS field names. Standardize them into one format.

For example:

```
{
  "title": "Example AI announcement",
  "url": "https://example.com/article",
  "source": "Example News",
  "published_at": "2026-11-05T08:00:00Z",
  "description": "A new AI model was announced.",
  "category": "artificial_intelligence"
}
```

Use an n8n Code node to map the incoming fields into this format.

### Step 5.3 — Filter to the last 7 days

Do not simply trust the RSS feed to return recent articles.

Use a Code node or your backend to compare publication dates against the current time.

Example JavaScript for an n8n Code node:

```
const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;

return items.filter(item => {
  const published = new Date(
    item.json.isoDate || item.json.pubDate
  ).getTime();

  return Number.isFinite(published) &&
         published >= cutoff &&
         published <= Date.now();
});
```

For production, also handle missing or malformed publication dates. Do not silently treat an unknown date as a recent article.

### Step 5.4 — Send articles to FastAPI

Add an HTTP Request node:

- Method: `POST`
- URL: `http://backend:8000/api/articles/ingest`
- Content Type: JSON
- Body: normalized article data

The exact URL depends on your Docker network. When n8n and FastAPI run in the same Compose network, use the backend service name, not `localhost`.

The backend should validate, deduplicate, and store the articles.

## 6. Build the FastAPI backend

The backend is where most of the engineering work should happen.

### Step 6.1 — Create the Python environment

From the project root:

```
cd backend

python3 -m venv .venv
source .venv/bin/activate

pip install fastapi uvicorn sqlalchemy \
  psycopg[binary] pydantic-settings \
  feedparser httpx python-dotenv \
  pytest
```

Save dependencies:

```
pip freeze > requirements.txt
```

### Step 6.2 — Create your API endpoints

Start with these endpoints:

| Method | Endpoint                     | Purpose                            |
| ------ | ---------------------------- | ---------------------------------- |
| POST   | `/api/articles/ingest`       | Receive articles from n8n          |
| GET    | `/api/articles`              | Retrieve stored articles           |
| GET    | `/api/articles/{id}`         | Retrieve one article               |
| POST   | `/api/articles/{id}/analyze` | Analyze an article                 |
| GET    | `/api/reports/daily`         | Retrieve daily intelligence report |
| GET    | `/api/trends`                | Retrieve detected trends           |
| GET    | `/health`                    | Check API availability             |

Your initial `main.py` can be simple:

```
from fastapi import FastAPIapp = FastAPI(title="SignalDesk API")@app.get("/health")def health():    return {"status": "healthy"}@app.post("/api/articles/ingest")def ingest_articles():    return {"message": "Ingestion endpoint ready"}
```

Run it:

```
uvicorn app.main:app --reload --host 0.0.0.0
```

Open the automatic API documentation:

`http://localhost:8000/docs`

### Step 6.3 — Design the database

You need to store more than article titles and links.

I recommend these initial tables:

Articles

| Field        | Type      | Purpose                              |
| ------------ | --------- | ------------------------------------ |
| id           | UUID      | Unique identifier                    |
| title        | TEXT      | Article title                        |
| url          | TEXT      | Original article URL                 |
| source       | TEXT      | Publisher                            |
| published_at | TIMESTAMP | Publication date                     |
| description  | TEXT      | Article description                  |
| content      | TEXT      | Extracted article text, if available |
| category     | TEXT      | Assigned category                    |
| content_hash | TEXT      | Exact duplicate detection            |
| created_at   | TIMESTAMP | Ingestion date                       |

AI analyses

| Field          | Type      | Purpose              |
| -------------- | --------- | -------------------- |
| id             | UUID      | Unique identifier    |
| article_id     | UUID      | Associated article   |
| summary        | TEXT      | AI-generated summary |
| importance     | INTEGER   | Importance score     |
| relevance      | INTEGER   | Relevance score      |
| key_points     | JSONB     | Important findings   |
| why_it_matters | TEXT      | Explanation          |
| model          | TEXT      | Model used           |
| created_at     | TIMESTAMP | Analysis date        |

Topics

- id
- name
- description
- keywords

Article topics

- article_id
- topic_id

Trends

- id
- title
- description
- category
- confidence
- first_detected_at
- last_detected_at

Use database migrations (Alembic) once the initial schema is established.

### Step 6.4 — Implement duplicate detection

Duplicate detection is important because the same announcement can appear on multiple websites.

Use several layers:

1. URL matching: Normalize URLs and check whether the article already exists.
2. Content hashing: Generate a hash from the normalized title and source content.
3. Semantic matching: Use embeddings to identify articles discussing substantially the same event.

For example:

- Publisher A: "NVIDIA announces new AI chip."
- Publisher B: "NVIDIA reveals next-generation AI processor."
- Publisher C: "New NVIDIA GPU architecture announced."

These may represent the same underlying story.

Use PostgreSQL constraints to prevent duplicate URL records. Add pgvector later for semantic matching. Avoid merging articles solely because their titles look similar; two separate announcements from the same company may be related but distinct.

## 7. Add AI analysis

This is where SignalDesk becomes more than an RSS reader.

You want the AI to analyze every new article and produce structured information.

### Step 7.1 — Choose an AI model

You have two practical routes:

Option A — Cloud API

Recommended for initial development

- OpenAI API or another hosted LLM.
- Easier to deploy.
- More predictable performance.
- Requires API credentials and has usage costs.

Option B — Local LLM

- LM Studio or Ollama.
- Can run on your Legion.
- No per-token API charge.
- Performance and context limits depend on the model and available hardware.

My recommendation: build the AI integration so you can switch between providers without rewriting your application.

Create a common interface such as:

```
class AIProvider:    def analyze_article(self, article):        raise NotImplementedError
```

Then implement separate providers for hosted and local models.

### Step 7.2 — Create the AI analysis prompt

The model should return structured JSON, not an unstructured essay.

Here is a starting prompt:

# SignalDesk — Article Intelligence Analysis

You are an analytical research assistant for a technology and current-events intelligence platform.

Analyze the supplied article using only the information provided. Do not invent facts, statistics, quotes, or events.

## Requirements

1. Identify the primary subject.
2. Assign one primary category:
   - artificial_intelligence
   - software_engineering
   - computer_science
   - cybersecurity
   - hardware
   - business
   - finance
   - science
   - formula_one
   - other
3. Write a concise summary of the article.
4. Extract the most important facts and developments.
5. Explain why this development matters.
6. Identify potential implications for developers, businesses, or consumers.
7. Score importance from 1–10.
8. Score relevance to technology and software engineering from 1–10.
9. Identify whether the article reports a confirmed development, an opinion, speculation, or an announcement.
10. Identify any uncertainty or missing context.

## Output format

Return valid JSON:

{\
"category": "artificial_intelligence",\
"summary": "A concise factual summary.",\
"key_points": [\
"Important fact one",\
"Important fact two"\
],\
"why_it_matters": "Explain the significance.",\
"implications": [\
"Potential implication one"\
],\
"importance_score": 8,\
"relevance_score": 9,\
"content_type": "announcement",\
"certainty": "confirmed",\
"uncertainties": [],\
"tags": ["AI", "LLMs", "research"]\
}

Do not include Markdown fences or commentary outside the JSON.

## Article

Title: {{title}}

Publisher: {{source}}

Publication date: {{published_at}}

Description: {{description}}

Article text: {{content}}

Use a JSON schema or Pydantic model to validate the response. If the model returns invalid JSON, retry once or mark the analysis as failed. Do not let malformed AI output break the ingestion workflow.

### Step 7.3 — Store the analysis

When the AI finishes:

1. Validate the JSON.
2. Convert it to your database schema.
3. Save the analysis.
4. Link it to the original article.
5. Record the model name and analysis timestamp.

Keep the original article and AI output separate. That allows you to reprocess old articles when you improve your prompts or change models.

### Step 7.4 — Add AI quality controls

This is important if you want to make the project credible.

- Preserve the original article URL.
- Clearly label AI-generated summaries.
- Never present model-generated implications as confirmed facts.
- Track model and prompt versions.
- Handle unavailable article text.
- Reject unsupported claims where possible.
- Avoid sending excessively long article text to the model.
- Make failed analyses visible rather than silently dropping them.

If you only have an RSS description, tell the model it has a description rather than the full article. It must not imply it read the full article.

## 8. Build the second n8n workflow: AI processing

The ingestion workflow should store articles. A separate workflow should process new articles.

Workflow 2 — AI article processing

Schedule Trigger

Every 15 minutes

HTTP Request

GET unprocessed articles from FastAPI

Loop Over Items

Process articles individually or in controlled batches

AI analysis

Classify, summarize, score, extract key points

HTTP Request

POST validated analysis back to FastAPI

PostgreSQL

Save analysis and mark article as processed

You can call the AI provider directly from n8n, but I recommend keeping the AI integration in FastAPI. That gives you better testing, structured output validation, model switching, and control over retries.

In that design, n8n calls an endpoint such as:

```
POST /api/articles/process-pending
```

FastAPI then handles the AI work.

## 9. Add daily intelligence reports

A collection of summaries is not yet an intelligence platform. You need to identify what is important across all the articles.

Create a third workflow:

Workflow 3 — Daily intelligence report

Schedule Trigger

Every day at 7:00 AM

Retrieve analyzed articles

Collect the last 24 hours of relevant articles

Trend detection

Find recurring developments across publishers

AI report generation

Generate a concise, evidence-linked report

Save report

Store report in PostgreSQL for dashboard access

### What should the report contain?

I would use these sections:

1. Top 5 developments: Most important stories of the day.
2. AI and machine learning: New models, research, benchmarks, and releases.
3. Software engineering: Frameworks, programming, databases, and developer tools.
4. Hardware and infrastructure: GPUs, CPUs, chips, and data centers.
5. Business and markets: Major developments in technology companies.
6. Formula 1: Relevant race, team, and Alpine developments.
7. Emerging trends: Themes appearing across multiple sources.
8. What to learn: Technologies or concepts worth investigating.

Each story should include its original source, publication date, and a link.

### Trend detection

Do not rely on the AI simply declaring something a trend.

A better approach:

1. Group articles by category.
2. Generate or retrieve their embeddings.
3. Find semantically similar articles.
4. Group related articles into clusters.
5. Count independent sources and publication frequency.
6. Ask AI to describe the underlying development.
7. Store a trend with supporting article IDs.

For example, if multiple independent sources report that smaller AI models are becoming more capable, the system might identify a trend around efficient local inference.

The report should distinguish between:

- A single announcement.
- A recurring topic.
- A genuinely emerging trend supported by multiple independent sources.

## 10. Build the frontend dashboard

Once ingestion and analysis work, build the user interface.

I recommend Next.js, TypeScript, Tailwind, and shadcn/ui.

### Main dashboard

[EyesPro — منصّة إدارة ونشر الأخبار الاحترافية | الإصدار v1.0.8](https://images.openai.com/static-rsc-4/e1qnyg8CBgsxDEzYlK3r6WOtDqSMM5CsWx3KtApGFX7XTDti0KE0jKXwsNhjgNpX7dvJpDCRclEss9eCxATz2BwPRiCW49hHSmkZPJI5JLP25-TbcGxdLjgWHG67ULnw6k5Zg2HWP56xZT9kgcrNVSsKkelqm7wA21jveB9fh74?purpose=inline)

[Sentinel – News Intelligence Dashboard Design by Armansyah Hakim on Dribbble](https://images.openai.com/static-rsc-4/-pyqDmIEE0txCjPpZOCwy2s5j6O0p-xzyjXknJ22gUtq1VWTjxUQfzZ7N4Y2ZmyJq8FCIZ-n7qKmbSKu_7qloGxC5NT60TKb27yL79OBN2BDgv_nlvEn1xyFwo3llbnu7b1_-0wStACfkUbOAXgzMRsSUsnsmTFcIo__jX27VZ8?purpose=inline)

[AI Digest - Stay Ahead, Save Time, and Gain a Rapid Grasp of Evolving Topics – NewsWhip Support](https://images.openai.com/static-rsc-4/8ij6ZnxiuGP_9xbus4sRk6d57QRKxv3ypFB3HuqNqbpMkPzDRHnFwMRaYE28_9NwhVTkO2c75dYSrFmbzxo3FGzkNnxyNYOlKdlH0cVf-gbn9fodsNcxlwXHPq03XUny0mMB0fDaHNSW3oK_2pUu5TbTQrkiOIgubuK5yiI4e-E?purpose=inline)

12

Build these pages:

| Page        | Features                                    |
| ----------- | ------------------------------------------- |
| Dashboard   | Daily overview and top stories              |
| Latest News | All collected articles                      |
| AI Analysis | Summaries and implications                  |
| Trends      | Recurring topics and emerging developments  |
| Categories  | AI, software, hardware, finance, F1         |
| Search      | Search by keyword, source, or topic         |
| Reports     | Daily and weekly intelligence reports       |
| Settings    | Topic preferences and notification settings |

### Dashboard components

Your home page should display:

- Total articles collected this week.
- Articles analyzed.
- Top five stories.
- Trending topics.
- Recent AI research.
- Latest software developments.
- Daily intelligence report.
- Source distribution.

Use charts only where they provide useful information, such as article volume by category or changes in topic frequency.

### Article card

Every article card should show:

- Headline.
- Publisher.
- Publication date.
- Category.
- AI-generated summary.
- Importance score.
- Why it matters.
- Original source link.

Avoid showing AI-generated scores without explaining what they represent. For example, distinguish importance from personal relevance.

## 11. Add personalization

Once the basic platform works, allow users to customize the intelligence feed.

For example:

- Prioritize artificial intelligence.
- Follow local LLM development.
- Track Python and C++.
- Follow NVIDIA and AMD.
- Track Alpine F1.
- Exclude low-quality sources.
- Choose daily or weekly reports.

A user should be able to mark an article:

- Relevant
- Not relevant
- Already known
- Save for later

You can use this feedback to adjust ranking.

One important distinction: personalization should affect article ranking, not the underlying factual reporting.

## 12. Add reliability and monitoring

This is an important part of turning a prototype into a production-quality project.

Implement:

Ingestion reliability

- Retry failed RSS requests.
- Add request timeouts.
- Track unavailable feeds.
- Prevent duplicate ingestion.
- Record ingestion timestamps.

AI reliability

- Validate model output.
- Retry transient failures.
- Limit processing concurrency.
- Track token usage and costs.
- Record model and prompt versions.

Application reliability

- Add API tests.
- Add database integration tests.
- Add error logging.
- Add health checks.
- Use database transactions where appropriate.

Security

- Store API keys in environment variables or n8n credentials.
- Never commit `.env` files.
- Protect backend endpoints.
- Add authentication before making the dashboard public.
- Do not expose n8n's editor publicly without proper protection.

## 13. Deploy the application

When everything works locally, deploy the services.

A reasonable deployment arrangement:

| Service          | Deployment option         |
| ---------------- | ------------------------- |
| Next.js frontend | Vercel                    |
| FastAPI backend  | Railway, Render, or a VPS |
| PostgreSQL       | Managed PostgreSQL        |
| Redis            | Managed Redis             |
| n8n              | VPS or managed n8n        |
| Vector database  | pgvector in PostgreSQL    |

For a portfolio project, Docker Compose on a VPS is also a good option. It demonstrates that you understand deployment beyond simply deploying a frontend to Vercel.

Use GitHub Actions to:

- Run Python tests.
- Run frontend linting and type checking.
- Build Docker images.
- Run integration tests.
- Deploy when appropriate.

## 14. Recommended development schedule

I would give this project approximately six weeks. The goal is a functioning, deployed product, not just a visually impressive demo.

## Six-week development roadmap

1. Week 1 — Foundation
   - Set up GitHub repository.
   - Configure Docker and n8n.
   - Create FastAPI backend.
   - Configure PostgreSQL.
   - Connect 5–10 RSS sources.
   - Store normalized articles.

     Deliverable: working news ingestion
2. Week 2 — Data processing
   - Implement seven-day filtering.
   - Implement URL normalization.
   - Add duplicate detection.
   - Add database migrations.
   - Build ingestion tests.

     Deliverable: clean article database
3. Week 3 — AI integration
   - Integrate an LLM provider.
   - Implement structured AI output.
   - Add article classification.
   - Generate summaries.
   - Add importance and relevance scoring.
   - Add retry and validation logic.

     Deliverable: automated article analysis
4. Week 4 — Frontend
   - Build Next.js dashboard.
   - Create article cards.
   - Add category filtering.
   - Add search.
   - Display AI summaries and source links.

     Deliverable: usable web application
5. Week 5 — Intelligence
   - Implement semantic deduplication.
   - Build trend detection.
   - Generate daily reports.
   - Add user preferences.
   - Add feedback and ranking.

     Deliverable: personalized intelligence platform
6. Week 6 — Production readiness
   - Add automated tests.
   - Add GitHub Actions.
   - Configure deployment.
   - Add monitoring and logging.
   - Write technical documentation.
   - Record a product demo.

     Deliverable: deployed portfolio project

## 15. What makes this a strong portfolio project?

The difference between a basic automation and a serious engineering project is the technical depth.

| Basic implementation      | Strong implementation                          |
| ------------------------- | ---------------------------------------------- |
| Reads RSS feeds           | Multi-source ingestion pipeline                |
| Sends articles to ChatGPT | Structured AI analysis with validation         |
| Summarizes headlines      | Evidence-linked summaries and implications     |
| Removes identical URLs    | Semantic duplicate detection                   |
| Displays news             | Searchable intelligence dashboard              |
| Generates daily summaries | Trend detection across independent sources     |
| Runs manually             | Scheduled, monitored, fault-tolerant workflows |
| Uses one AI model         | Provider-independent AI architecture           |

For your portfolio, prioritize demonstrating:

1. Backend engineering: FastAPI, API design, database modeling, validation.
2. Automation: n8n workflows, scheduled jobs, retries, and error handling.
3. Applied AI: LLM integration, structured outputs, embeddings, and evaluation.
4. Data engineering: Ingestion, normalization, deduplication, and processing.
5. DevOps: Docker, CI/CD, deployment, and monitoring.

## 16. Definition of a finished MVP

Before adding more features, make sure you can demonstrate all of these:

MVP completion checklist

# 0/13

At least 5 working RSS sources

Automatic ingestion every 3 hours

Strict seven-day publication-date filtering

PostgreSQL persistence

Duplicate URL prevention

AI classification and structured summaries

Importance and relevance scoring

Original source links on every article

Search and category filtering

Daily intelligence report

Docker-based local setup

Automated backend and frontend tests

Public deployment and documented architecture

## 17. My recommendation for how to approach this

Do not start by building the frontend. Start with the data pipeline.

Your first milestone should be:

RSS feeds → n8n → FastAPI → PostgreSQL → verified stored articles.

Then add AI analysis. After that, build the dashboard.

This approach reduces the risk of spending two weeks designing a dashboard that has no reliable data behind it.

I would also keep the initial scope controlled:

- 5–10 RSS feeds.
- 6–8 categories.
- One AI provider initially.
- One daily report.
- No user accounts until the core system works.

Once that is reliable, expand it.

The final objective: SignalDesk should be something you can actually use every morning to understand the important developments from the previous seven days, not simply another AI wrapper around RSS feeds.

A logical next step is to build Week 1 together, starting with the GitHub repository, Docker Compose configuration, n8n setup, FastAPI backend, and PostgreSQL schema.
