from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import FastAPI, Depends, HTTPException, Form, Query, Security
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from fastapi import Request 
from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from fastapi.responses import FileResponse
from starlette.middleware.gzip import GZipMiddleware
import playwright._impl._errors as playwright_errors
import base64
import time
import uuid
import json
import base64
import os
from datetime import datetime
import os
from datetime import datetime
from bs4 import BeautifulSoup
import htmlmin
# Existing imports ke saath ye add karo:
from fastapi import BackgroundTasks  # <-- Ye add karna zaroori hai
from contextlib import asynccontextmanager # <-- Ye bhi add karo

# Hamare naye database functions import karo
from database import init_db, log_request_to_db, get_request_history, get_stats

from definitions import (
    ScreenshotResponse,
    MinimizeHTMLResponse,
    ExtractTextResponse,
    ResponseModel,
    ReaderResponse,
    MarkdownResponse,
)
import html2text
from readability import Document
from utils import generate_cache_key, optimize_image, create_thumbnail, smooth_scroll
import json
from PIL import Image
import io
import uuid
from config import setup_configurations, url_to_sha256_filename, hide_cookie_banners

# === RATE LIMITER SETUP ===
# Define a key function that uses IP address by default
def get_rate_limit_key(request: Request):
    # OPTIONAL: BYPASS IF API KEY MATCHES
    # If the user provides the correct API Key, we return a specific value 
    # that we can whitelist, OR we just let them pass. 
    # For now, we stick to IP-based limiting for everyone to keep it simple.
    return get_remote_address(request)

# Initialize the Limiter
limiter = Limiter(key_func=get_rate_limit_key)



@asynccontextmanager
async def lifespan(app: FastAPI):
    # Server start hone par DB initialize karo
    init_db(DATABASE_URL)
    yield
    # Server band hone par kuch karna ho toh yahan likho
app = FastAPI(
    title="Playwright-based Webpage Scraper API",
    description="""
    This API allows users to browse webpages, capture screenshots, minimize HTML content, and extract text from HTML.
    Built using **FastAPI** and **Playwright**, this API provides advanced browsing features, handling redirects, and capturing network details. 
    It is designed for automation, scraping, and content extraction.

    ## Features:
    - **Browse Endpoint**: Retrieve detailed information about a webpage including network data, logs, performance metrics, redirects, and more.
    - **Screenshot Endpoint**: Capture a screenshot of any given URL, with optional full-page capture.
    - **Minimize HTML Endpoint**: Minify HTML content by removing unnecessary comments and whitespace.
    - **Extract Text Endpoint**: Extract clean, plain text from provided HTML content.

    ## Authentication:
    - API uses optional Bearer token authentication. If an API key is set via the `API_KEY` environment variable, it must be provided in the Authorization header. Otherwise, no authentication is required.
    
    ## Usage:
    - The **Browse** endpoint can track redirects and capture detailed request and response data.
    - The **Screenshot** endpoint allows live capture or retrieval from cache.
    - Minify HTML or extract text from raw HTML via the **Minimize HTML** and **Extract Text** endpoints.
    """,
    
    version="1.0.0",
    lifespan=lifespan
)
# Connect the limiter to the app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(GZipMiddleware, minimum_size=500)
@app.exception_handler(RateLimitExceeded)
async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "error": "Too Many Requests",
            "detail": f"Whoa! Slow down. {exc.detail}",
            "limit": str(exc.limit),
            "retry_after": "1 minute"
        }
    )

cache, CACHE_EXPIRATION_SECONDS, security, API_KEY, DATABASE_URL = setup_configurations()


def optional_auth(
    credentials: HTTPAuthorizationCredentials = Security(security),
):
    """
    If API_KEY is "none", skip authentication.
    If API_KEY is set, enforce Bearer token authentication.
    """
    if API_KEY == "none":
        return None
    elif credentials:
        token = credentials.credentials
        if token == API_KEY:
            return credentials
        else:
            raise HTTPException(status_code=403, detail="Invalid API key")
    else:
        raise HTTPException(
            status_code=401, detail="Authorization header missing or invalid"
        )
