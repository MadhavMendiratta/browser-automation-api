# 🕷️ Browser Automation API

A high-performance, scalable scraping API built with **FastAPI** and **Playwright**. 

Unlike simple scrapers, this project features a complete **Data Platform** architecture with built-in request history, analytics, rate limiting, and caching.

## 🚀 Features

* **Headless Browsing:** Full JavaScript rendering using Chromium (Playwright).
* **Smart Caching:** Disk-based caching to prevent redundant scraping and speed up responses.
* **Database Logging:** Automatically tracks every request (URL, status, response time) in SQLite.
* **Analytics Dashboard:** Built-in endpoints (`/stats`, `/history`) to monitor API usage and health.
* **Rate Limiting:** IP-based traffic control (using SlowAPI) to prevent abuse.
* **Anti-Detection:** Custom logic to hide automation signals and block cookie banners.
* **Media Capture:** Capabilities for full-page screenshots, PDF generation, and video recording.

## 🛠️ Tech Stack

* **Framework:** FastAPI (Python 3.11+)
* **Engine:** Playwright (Async)
* **Database:** SQLite + SQLAlchemy
* **Caching:** DiskCache
* **Security:** SlowAPI (Rate Limiting)
* **Validation:** Pydantic

## ⚡ Getting Started

### 1. Clone the repository
```bash
git clone [https://github.com/yourusername/browser-automation-api.git](https://github.com/yourusername/browser-automation-api.git)
cd browser-automation-api