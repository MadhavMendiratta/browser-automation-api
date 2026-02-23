# Browser Automation API

A high-level web scraping and browser automation API built on FastAPI and Playwright. It exposes REST endpoints for headless browsing, screenshot capture, video recording, HTML processing, and content extraction — backed by SQLite-based request logging, disk caching, and a built-in analytics dashboard.

## Features

- **Headless Browsing** — Navigate any URL with full JavaScript execution, capturing network traffic, console logs, cookies, redirects, performance timing, downloads, screenshots, and session video in a single request.
- **Screenshot Capture** — On-demand viewport or full-page screenshots with configurable quality, automatic JPEG optimization, and thumbnail generation.
- **Video Recording** — Record browsing sessions as WebM files and stream them back via a dedicated endpoint.
- **HTML Minimization** — Minify raw HTML by stripping comments and whitespace.
- **Text Extraction** — Parse HTML and return clean plain text via BeautifulSoup.
- **Reader Mode** — Extract the main readable content and title from a page using the readability algorithm.
- **HTML-to-Markdown** — Convert HTML to Markdown with link preservation.
- **Cookie Banner Blocking** — Automatically detect and hide cookie/consent banners using an extensive selector list and heuristic content matching, including Shadow DOM and iframe traversal.
- **Smooth Scrolling** — Programmatic scroll-to-bottom for lazy-loaded and infinite-scroll pages.
- **Disk Cache** — Response caching via `diskcache` with configurable TTL to avoid redundant browser launches.
- **Rate Limiting** — Per-IP rate limits on all scraping endpoints via `slowapi`.
- **Request Logging & Analytics** — Every request is logged to SQLite (URL, endpoint, status, response time, cache hit). Aggregated stats (success rate, cache hit rate, top domains, endpoint distribution) are queryable via API.
- **Web Dashboard** — Server-rendered frontend (Jinja2 + TailwindCSS + HTMX + Alpine.js) with a scraper console, live activity feed, searchable request history, and analytics page with Chart.js visualizations.
- **Optional API Key Auth** — Bearer token authentication that can be disabled by setting the key to `none`.
- **GZip Compression** — Responses above 500 bytes are automatically compressed.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend Framework | FastAPI, Uvicorn |
| Browser Engine | Playwright (Chromium, Firefox, WebKit) |
| Database | SQLite via SQLAlchemy |
| Caching | diskcache |
| Rate Limiting | slowapi |
| HTML Parsing | BeautifulSoup, htmlmin, readability-lxml, html2text, lxml |
| Image Processing | Pillow |
| Data Validation | Pydantic |
| Frontend | Jinja2, TailwindCSS (CDN), HTMX, Alpine.js, Chart.js |
| Environment | python-dotenv |

## Project Structure

```
.
├── app.py                  # FastAPI application — all API and frontend routes
├── config.py               # Configuration loader, cache/auth/DB setup, cookie banner logic
├── database.py             # SQLAlchemy models, DB init, request logging, analytics queries
├── definitions.py          # Pydantic request/response models
├── utils.py                # Image optimization, cache key generation, smooth scroll, env loader
├── requirements.txt        # Pinned Python dependencies
├── static/
│   └── js/
│       └── main.js         # Frontend JS — toasts, clipboard, Chart.js initialization
├── templates/
│   ├── base.html           # Base layout — sidebar, navigation, TailwindCSS/HTMX/Alpine includes
│   ├── dashboard.html      # Scraper console with URL input, action selector, and result area
│   ├── history.html        # Searchable request history table
│   ├── stats.html          # Analytics page with KPI cards and Chart.js charts
│   └── partials/
│       ├── history_rows.html    # HTMX partial — table rows for history search
│       ├── recent_activity.html # HTMX partial — live activity feed items
│       └── result_card.html     # HTMX partial — tabbed scraping result card
├── cache/                  # Disk cache storage (auto-generated)
├── downloads/              # Temporary download directory for browser file downloads
└── videos/                 # Temporary directory for recorded session videos
```

## Installation & Setup

### Prerequisites

- Python 3.10+
- pip

### Clone

```bash
git clone <repository-url>
cd browser-automation-api
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Install Playwright Browsers

```bash
playwright install
```

This downloads the Chromium, Firefox, and WebKit binaries required by Playwright.

## Environment Variables

Create a `.env` file in the project root. All variables are optional and have sensible defaults.

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | `none` | Bearer token for endpoint authentication. Set to `none` to disable auth. |
| `DATABASE_URL` | `sqlite:///./scraproxy.db` | SQLAlchemy database connection string. |
| `CACHE_EXPIRATION_SECONDS` | `3600` | TTL in seconds for cached responses. |
| `PLAYWRIGHT_BROWSERS_PATH` | `0` (bundled) | Custom path for Playwright browser binaries. |

## Running the Project

```bash
uvicorn app:app --reload
```

The server starts at `http://127.0.0.1:8000`. The interactive API docs are available at `/docs` (Swagger UI) and `/redoc`.

## API Endpoints

### Scraping

| Method | Path | Description | Rate Limit |
|--------|------|-------------|------------|
| `GET` | `/browse` | Full browser session — returns network data, logs, cookies, redirects, performance metrics, screenshot, thumbnail, and video. | 20/min |
| `GET` | `/screenshot` | Capture a viewport or full-page screenshot. Supports `live` mode to bypass cache. | 15/min |
| `GET` | `/video` | Record a browsing session and return the video file (WebM). | 30/min |

### HTML Processing

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/minimize` | Minify HTML (form field: `html`). |
| `POST` | `/extract_text` | Extract plain text from HTML (form field: `html`). |
| `POST` | `/reader` | Extract main readable content and title (form field: `html`). |
| `POST` | `/markdown` | Convert HTML to Markdown (form field: `html`). |

### Analytics

| Method | Path | Description | Rate Limit |
|--------|------|-------------|------------|
| `GET` | `/history` | Return the last N logged requests (default 50). | 60/min |
| `GET` | `/stats` | Aggregated usage statistics — totals, success rate, cache rate, top domains. | 60/min |

### Frontend

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Dashboard — scraper console with live activity feed. |
| `GET` | `/history-page` | Request history table with search. |
| `GET` | `/stats-page` | Analytics page with KPI cards and charts. |
| `POST` | `/scrape-htmx` | HTMX endpoint — runs a scrape and returns a tabbed result card partial. |
| `GET` | `/history-search` | HTMX partial — filters history rows by query. |
| `GET` | `/components/recent-activity` | HTMX partial — last 5 requests for the live feed. |

### System

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check — returns `{"status": "ok"}`. |

## Usage

### Browse a URL

```bash
curl "http://127.0.0.1:8000/browse?url=https://example.com&cookiebanner=true&scroll=true"
```

### Take a Screenshot

```bash
curl "http://127.0.0.1:8000/screenshot?url=https://example.com&full_page=true&quality=90"
```

### Record a Video

```bash
curl -o session.webm "http://127.0.0.1:8000/video?url=https://example.com&width=1280&height=720"
```

### Convert HTML to Markdown

```bash
curl -X POST "http://127.0.0.1:8000/markdown" -F "html=<h1>Hello</h1><p>World</p>"
```

### With API Key Authentication

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" "http://127.0.0.1:8000/browse?url=https://example.com"
```

## Future Improvements

- Scheduled/recurring scrape jobs with a task queue (Celery or ARQ).
- Per-user API key management with usage quotas and tiered rate limits.
- Proxy rotation support for geo-distributed or stealth scraping.
- WebSocket-based live progress streaming during long browse sessions.
- Export request history and analytics data as CSV/JSON.
- Pagination for the `/history` endpoint and frontend table.
- Containerized deployment with Docker and docker-compose.
- Configurable browser viewport dimensions and user-agent strings per request.
- Persistent video storage with presigned download URLs instead of inline base64.

## Contributing

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/your-feature`).
3. Commit your changes (`git commit -m "Add your feature"`).
4. Push to the branch (`git push origin feature/your-feature`).
5. Open a Pull Request.