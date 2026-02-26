# Browser Automation API

A production-grade web scraping and browser automation service built on FastAPI and Playwright. It provides REST endpoints for headless browsing, screenshot capture, video recording, HTML processing, and content extraction, backed by PostgreSQL request logging, disk caching, JWT authentication, and a server-rendered analytics dashboard.

## Features

- **Headless Browsing** — Navigate any URL with full JavaScript execution, capturing network traffic, console logs, cookies, redirects, performance timing, downloads, screenshots, and session video in a single request.
- **Screenshot Capture** — On-demand viewport or full-page screenshots with configurable JPEG quality, automatic optimization via Pillow, and thumbnail generation.
- **Video Recording** — Record browsing sessions as WebM files and return them as downloadable responses or base64-encoded payloads.
- **HTML Minimization** — Minify raw HTML by stripping comments and whitespace.
- **Text Extraction** — Parse HTML and return clean plain text via BeautifulSoup.
- **Reader Mode** — Extract the main readable content and title from a page using the readability algorithm.
- **HTML-to-Markdown** — Convert HTML to Markdown with link preservation.
- **Cookie Banner Blocking** — Automatically detect and hide cookie/consent/GDPR banners using an extensive CSS selector list and heuristic content matching, including Shadow DOM traversal and same-origin iframe scanning.
- **Smooth Scrolling** — Programmatic scroll-to-bottom for lazy-loaded and infinite-scroll pages, with configurable duration and pause intervals.
- **Disk Cache** — Response caching via `diskcache` with configurable TTL to avoid redundant browser launches.
- **Rate Limiting** — Per-IP rate limits on all scraping and auth endpoints via `slowapi`.
- **JWT Authentication** — Full user registration, login, token refresh, and password reset flow using JWT access/refresh tokens and bcrypt password hashing. Refresh tokens are stored as HTTP-only cookies.
- **Optional API Key Auth** — Bearer token authentication on scraping endpoints. Set the key to `none` to disable.
- **Request Logging and Analytics** — Every scraping request is logged to PostgreSQL (URL, endpoint, status code, response time, cache hit, associated user). Aggregated stats (success rate, cache hit rate, top domains, endpoint distribution) are queryable via API and rendered in the dashboard.
- **Web Dashboard** — Server-rendered frontend (Jinja2 + TailwindCSS + HTMX + Alpine.js) with a scraper console, live activity feed, searchable request history, and analytics page with Chart.js visualizations.
- **User-Scoped Data** — Authenticated users see only their own request history and statistics across the dashboard and API.
- **GZip Compression** — Responses above 500 bytes are automatically compressed.
- **Docker Support** — Dockerfile, docker-compose configuration with PostgreSQL and Redis services, and an entrypoint script with database health checks.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend Framework | FastAPI, Uvicorn |
| Browser Engine | Playwright (Chromium) |
| Database | PostgreSQL 15, SQLAlchemy 2.0, psycopg2 |
| Authentication | python-jose (JWT), passlib + bcrypt |
| Caching | diskcache |
| Rate Limiting | slowapi |
| HTML Parsing | BeautifulSoup4, htmlmin, readability-lxml, html2text, lxml |
| Image Processing | Pillow |
| Data Validation | Pydantic v2, email-validator |
| Frontend | Jinja2, TailwindCSS (CDN), HTMX, Alpine.js, Chart.js |
| Infrastructure | Docker, Docker Compose, PostgreSQL, Redis |
| Environment | python-dotenv |

## Project Structure

```
.
├── app.py                  # FastAPI application — API endpoints and frontend routes
├── config.py               # Configuration loader (cache, auth, DB URL, cookie banner logic)
├── database.py             # SQLAlchemy models (User, ScrapingRequest), DB init, logging, analytics
├── definitions.py          # Pydantic request/response schemas
├── utils.py                # Image optimization, cache key generation, smooth scroll
├── rate_limit.py           # Shared slowapi Limiter instance
├── auth/
│   ├── __init__.py         # Exports auth_router
│   ├── routes.py           # Auth API routes (register, login, refresh, forgot/reset password)
│   ├── security.py         # JWT creation/decoding, bcrypt hashing, token configuration
│   ├── schemas.py          # Pydantic models for auth requests/responses with validators
│   └── dependencies.py     # FastAPI dependencies for current user resolution (Bearer + cookie)
├── static/
│   └── js/
│       └── main.js         # Frontend JS — toast notifications, clipboard, Chart.js init
├── templates/
│   ├── base.html           # Base layout — sidebar navigation, CDN includes, toast container
│   ├── dashboard.html      # Scraper console with URL input, action picker, and result area
│   ├── history.html        # Searchable request history table
│   ├── stats.html          # Analytics page with KPI cards and Chart.js charts
│   ├── auth/
│   │   ├── login.html      # Login form
│   │   ├── register.html   # Registration form
│   │   ├── forgot_password.html  # Forgot password form
│   │   └── reset_password.html   # Password reset form
│   └── partials/
│       ├── history_rows.html     # HTMX partial — filtered history table rows
│       ├── recent_activity.html  # HTMX partial — live activity feed items
│       └── result_card.html      # HTMX partial — tabbed scraping result card
├── Dockerfile              # Python 3.11 slim image with Playwright Chromium
├── docker-compose.yml      # App + PostgreSQL + Redis services
├── entrypoint.sh           # Waits for PostgreSQL readiness, then starts Uvicorn
├── requirements.txt        # Pinned Python dependencies
├── cache/                  # Disk cache storage (auto-generated)
├── downloads/              # Temporary directory for browser file downloads
└── videos/                 # Temporary directory for recorded session videos
```

## Installation and Setup

### Prerequisites

- Python 3.10+
- PostgreSQL 15+ (or Docker)
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
playwright install --with-deps chromium
```

### Set Up PostgreSQL

Create a database and user, or use the provided Docker Compose setup (see [Docker Deployment](#docker-deployment)).

## Environment Variables

Create a `.env` file in the project root.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string. Example: `postgresql+psycopg2://user:pass@localhost:5432/scraper` |
| `SECRET_KEY` | Yes (production) | `change-me-in-production` | Secret key for JWT signing. Must be changed in production. |
| `API_KEY` | No | `none` | Bearer token for scraping endpoint auth. Set to `none` to disable. |
| `CACHE_EXPIRATION_SECONDS` | No | `3600` | TTL in seconds for cached responses. |
| `PLAYWRIGHT_BROWSERS_PATH` | No | `0` (bundled) | Custom path for Playwright browser binaries. |
| `PORT` | No | `8000` | Server port (used by Docker/Railway). |
| `POSTGRES_HOST` | No | `postgres` | PostgreSQL host for the entrypoint health check. |
| `POSTGRES_PORT` | No | `5432` | PostgreSQL port for the entrypoint health check. |

Example `.env`:

```
DATABASE_URL=postgresql+psycopg2://admin:admin@localhost:5432/scraper
SECRET_KEY=your-random-secret-key-here
API_KEY=none
CACHE_EXPIRATION_SECONDS=3600
```

## Running the Project

### Local

```bash
uvicorn app:app --reload
```

The server starts at `http://127.0.0.1:8000`. Interactive API docs are at `/docs` (Swagger UI) and `/redoc`.

### Docker Deployment

```bash
docker compose up --build
```

This starts three services:
- **app** — The FastAPI application on port `8000`
- **postgres** — PostgreSQL 15 on port `5432` (user: `admin`, password: `admin`, database: `scraper`)
- **redis** — Redis 7 on port `6379`

The entrypoint script automatically waits for PostgreSQL to become available before starting the application.

## API Endpoints

### Authentication

| Method | Path | Description | Rate Limit |
|--------|------|-------------|------------|
| `POST` | `/auth/register` | Register a new user. | 3/min |
| `POST` | `/auth/login` | Authenticate and receive an access token. Sets refresh token cookie. | 5/min |
| `POST` | `/auth/refresh` | Issue a new access token using the refresh token cookie. | — |
| `GET` | `/auth/me` | Return the current authenticated user's details. | — |
| `POST` | `/auth/forgot-password` | Generate a password reset token (logged to console). | 3/min |
| `POST` | `/auth/reset-password` | Reset password using a valid reset token. | 5/min |

### Scraping

| Method | Path | Description | Rate Limit |
|--------|------|-------------|------------|
| `GET` | `/browse` | Full browser session — network data, logs, cookies, redirects, performance metrics, screenshot, thumbnail, and video. | 20/min |
| `GET` | `/screenshot` | Viewport or full-page screenshot with configurable quality and thumbnail size. Supports `live` mode to bypass cache. | 15/min |
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
| `GET` | `/history` | Return the last N logged requests (default: 50). Scoped to current user if authenticated. | 60/min |
| `GET` | `/stats` | Aggregated usage statistics. Scoped to current user if authenticated. | 60/min |

### Frontend Pages

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Dashboard — scraper console with live activity feed. Requires login. |
| `GET` | `/history-page` | Request history table with search. Requires login. |
| `GET` | `/stats-page` | Analytics page with KPI cards and charts. Requires login. |
| `GET` | `/login` | Login page. |
| `GET` | `/register` | Registration page. |
| `GET` | `/logout` | Clear session and redirect to login. |
| `GET` | `/forgot-password` | Forgot password page. |
| `GET` | `/reset-password` | Password reset page (requires token query param). |
| `POST` | `/scrape-htmx` | HTMX endpoint — runs a scrape and returns a tabbed result partial. |
| `GET` | `/history-search` | HTMX partial — filters history rows by query string. |
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

### Register and Authenticate

```bash
# Register
curl -X POST "http://127.0.0.1:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@example.com","password":"SecurePass1","confirm_password":"SecurePass1"}'

# Login (returns access token, sets refresh cookie)
curl -X POST "http://127.0.0.1:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"SecurePass1"}' \
  -c cookies.txt

# Authenticated request
curl -H "Authorization: Bearer <access_token>" "http://127.0.0.1:8000/history"
```

### With API Key Authentication

If `API_KEY` is set to a value other than `none`:

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" "http://127.0.0.1:8000/browse?url=https://example.com"
```

## Future Improvements

- Scheduled/recurring scrape jobs with a task queue (Celery or ARQ backed by the existing Redis service).
- Email delivery integration for password reset tokens (currently logged to console).
- Per-user API key management with usage quotas and tiered rate limits.
- Proxy rotation support for geo-distributed or stealth scraping.
- WebSocket-based live progress streaming during long browse sessions.
- Export request history and analytics as CSV/JSON.
- Pagination for the `/history` endpoint and frontend table.
- Configurable browser viewport dimensions and user-agent strings per request.
- Persistent video storage with presigned download URLs instead of inline base64.
- HTTPS and secure cookie enforcement for production deployments.

## Contributing

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/your-feature`).
3. Commit your changes (`git commit -m "Add your feature"`).
4. Push to the branch (`git push origin feature/your-feature`).
5. Open a Pull Request.