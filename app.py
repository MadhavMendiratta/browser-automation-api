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


@app.get("/browse", response_model=ResponseModel)
@limiter.limit("20/minute")
async def browse(
    request: Request,
    url: str,
    background_tasks: BackgroundTasks,
    method: str = "GET",
    post_data: str = None,
    browser_name: str = "chromium",
    cookiebanner: bool = Query(False, description="Attempt to close cookie banners"),
    scroll: bool = Query(False, description="Attempt to scroll down the page."),
    credentials: HTTPAuthorizationCredentials = Depends(optional_auth),
):
    start_time = time.time()
    """
    Browse a webpage and gather various details including network data, logs, performance metrics, screenshots, and a video of the session.
    """
    try:
        cache_key = generate_cache_key(f"{url}-{method}-{post_data}-{browser_name}")
        request_uuid_map = {}

        if cache_key in cache:
            # === DB LOGGING (CACHE HIT) ===
            process_time = time.time() - start_time
            background_tasks.add_task(log_request_to_db, url, "browse", 200, process_time, True, None)
            return JSONResponse(content=json.loads(cache[cache_key]))

        async with async_playwright() as p:
            browser_type = getattr(p, browser_name, None)
            if browser_type is None:
                raise HTTPException(status_code=400, detail=f'Browser "{browser_name}" is not supported')

            download_dir = os.path.join(os.getcwd(), "downloads")
            os.makedirs(download_dir, exist_ok=True)

            # Set up video recording directory
            video_dir = os.path.join(os.getcwd(), "videos")
            os.makedirs(video_dir, exist_ok=True)

            # Launch browser with video recording enabled
            browser = await browser_type.launch(headless=True)
            context = await browser.new_context(
                accept_downloads=True,
                record_video_dir=video_dir,
                record_video_size={"width": 640, "height": 360},
            )
            page = await context.new_page()

            network_data = []
            logs = []
            redirects = []
            performance_metrics = {}
            downloaded_files = []

            # Variable to track main response status
            main_response_status = 200

            async def log_request(request):
                try:
                    request_uuid = str(uuid.uuid4())
                    request_uuid_map[request] = request_uuid

                    timing = request.timing or {}

                    try:
                        headers = await request.all_headers()
                    except Exception as e:
                        headers = "Unavailable due to error"
                        logs.append({"warning": f"Failed to fetch request headers: {str(e)}"})

                    try:
                        cookies = await context.cookies()
                    except Exception as e:
                        cookies = "Unavailable due to error"
                        logs.append({"warning": f"Failed to fetch cookies: {str(e)}"})

                    redirected_from_url = (
                        request.redirected_from.url if request.redirected_from else None
                    )
                    redirected_to_url = (
                        request.redirected_to.url if request.redirected_to else None
                    )

                    network_data.append(
                        {
                            "uuid": request_uuid,
                            "network": "request",
                            "url": request.url,
                            "method": request.method,
                            "headers": headers,
                            "cookies": cookies,
                            "resource_type": request.resource_type,
                            "redirected_from": redirected_from_url,
                            "redirected_to": redirected_to_url,
                            "timing": timing,
                            "sizes": await request.sizes(),
                            "request_time": datetime.now().isoformat(),
                        }
                    )

                except Exception as e:
                    logs.append({"error": f"An error occurred while logging the request: {str(e)}"})

            async def log_response(response):
                nonlocal main_response_status # Allow updating the outer variable
                try:
                    request = response.request
                    request_uuid = request_uuid_map.get(request)

                    timing = request.timing or {}

                    try:
                        request_headers = await request.all_headers()
                    except Exception as e:
                        request_headers = "Unavailable due to error"
                        logs.append({"warning": f"Failed to fetch request headers: {str(e)}"})

                    try:
                        response_headers = await response.all_headers()
                    except Exception as e:
                        response_headers = "Unavailable due to error"
                        logs.append({"warning": f"Failed to fetch response headers: {str(e)}"})

                    status_code = response.status
                    
                    # Capture the status code if this response matches our target URL
                    if response.url == url or response.url.rstrip('/') == url.rstrip('/'):
                         main_response_status = status_code

                    response_body = None
                    response_size = 0

                    try:
                        content_type = response_headers.get("content-type", "")
                        if "text" in content_type or "json" in content_type:
                            response_body = await response.text()
                            response_size = len(response_body)
                        else:
                            body = await response.body()
                            response_body = base64.b64encode(body).decode("utf-8")
                            response_size = len(body)
                    except Exception as e:
                        response_body = "Response body unavailable due to error"
                        logs.append({"warning": f"Failed to fetch response body: {str(e)}"})

                    try:
                        cookies = await context.cookies()
                    except Exception as e:
                        cookies = "Unavailable due to error"
                        logs.append({"warning": f"Failed to fetch cookies: {str(e)}"})

                    try:
                        security_details = await response.security_details()
                    except Exception as e:
                        security_details = "Unavailable due to error"
                        logs.append({"warning": f"Failed to fetch security details: {str(e)}"})

                    try:
                        server_address = await response.server_addr()
                    except Exception as e:
                        server_address = "Unavailable due to error"
                        logs.append({"warning": f"Failed to fetch server address: {str(e)}"})

                    redirected_to_url = (
                        request.redirected_to.url if request.redirected_to else None
                    )
                    redirected_from_url = (
                        request.redirected_from.url if request.redirected_from else None
                    )

                    network_data.append(
                        {
                            "uuid": request_uuid,
                            "network": "response",
                            "url": response.url,
                            "status": response.status,
                            "response_size": response_size,
                            "cookies": cookies,
                            "security": security_details,
                            "server": server_address,
                            "resource_type": request.resource_type,
                            "redirected_to": redirected_to_url,
                            "redirected_from": redirected_from_url,
                            "timing": timing,
                            "request_headers": request_headers,
                            "response_headers": response_headers,
                            "response_body": response_body,
                            "response_time": datetime.now().isoformat(),
                        }
                    )

                    if request.redirected_from:
                        redirects.append(
                            {
                                "step": len(redirects) + 1,
                                "from": request.redirected_from.url,
                                "to": request.url,
                                "status_code": status_code,
                                "server": server_address,
                                "resource_type": request.resource_type,
                            }
                        )

                except Exception as e:
                    logs.append({"error": f"An error occurred while logging the response: {str(e)}"})

            def log_console(msg):
                try:
                    logs.append({"console_message": msg.text})
                except Exception:
                    pass

            def log_js_error(error):
                try:
                    logs.append({"javascript_error": str(error)})
                except Exception:
                    pass

            page.on("request", log_request)
            page.on("response", log_response)
            page.on("console", log_console)
            page.on("pageerror", log_js_error)

            async def handle_download(download):
                path = await download.path()
                file_name = download.suggested_filename
                with open(path, "rb") as f:
                    file_content = base64.b64encode(f.read()).decode("utf-8")
                    downloaded_files.append(
                        {"file_name": file_name, "file_content": file_content}
                    )
                os.remove(path)

            page.on("download", handle_download)

            try:
                # Navigate to the URL
                if method == "POST" and post_data:
                    await page.goto(url, method=method, post_data=post_data)
                else:
                    await page.goto(url)

                # Wait for the page to stabilize (with timeout handling)
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=30000)
                except PlaywrightTimeoutError:
                    logs.append({"warning": "Initial page load timed out, proceeding with current state."})

                # Attempt to close cookie banners, if applicable
                if cookiebanner:
                    await hide_cookie_banners(page)

                # Final wait to ensure the page is stable after banner interaction
                try:
                    await page.wait_for_load_state("networkidle", timeout=30000)
                except PlaywrightTimeoutError:
                    logs.append({"warning": "Final load state timed out after banner interaction."})

            except PlaywrightTimeoutError:
                logs.append({"error": "Overall navigation timed out completely."})

            try:
                await page.wait_for_load_state("load", timeout=30000)
                title = await page.title()
            except PlaywrightTimeoutError:
                title = "Title unavailable due to load timeout"
                logs.append({"warning": "Page load timed out, title retrieval may be unstable."})
            except Exception as e:
                title = "Title unavailable due to error"
                logs.append({"error": f"Failed to retrieve title due to error: {str(e)}"})

            try:
                # Ensure the page is fully loaded, not just network idle
                await page.wait_for_load_state("load", timeout=30000)

                # Check if the meta description is available, with fallback logging
                meta_description = await page.locator("meta[name='description']").get_attribute("content")
                if not meta_description:
                    meta_description = "No Meta Description"
            except PlaywrightTimeoutError:
                meta_description = "Meta description unavailable due to load timeout"
                logs.append({"warning": "Page load timed out, meta description retrieval may be unstable."})
            except Exception as e:
                meta_description = "Meta description unavailable due to error"
                logs.append({"error": f"Failed to retrieve meta description due to error: {str(e)}"})

            # Get performance metrics
            performance_timing = await page.evaluate("window.performance.timing.toJSON()")
            performance_metrics["performance_timing"] = performance_timing

            cookies = await context.cookies()

            # Capture screenshot
            screenshot = await page.screenshot()
            image = Image.open(io.BytesIO(screenshot))
            full_optimized = optimize_image(image, quality=85)
            thumbnail_image = create_thumbnail(image, max_size=450)
            screenshot_b64 = base64.b64encode(full_optimized).decode("utf-8")
            thumbnail_b64 = base64.b64encode(thumbnail_image).decode("utf-8")

            if scroll:
                await smooth_scroll(page)

            # Close context to save video
            await context.close()
            await browser.close()

            # Retrieve video path
            video_file_path = await page.video.path()

            # Read and encode the video file
            with open(video_file_path, "rb") as video_file:
                video_base64 = base64.b64encode(video_file.read()).decode("utf-8")

            # Clean up the video file
            os.remove(video_file_path)
            
            # Helper to fill redirects if not captured
            if not redirects:
                for netw in network_data:
                    if netw["network"] == "response":
                        redirects.append(
                            {
                                "step": 0,
                                "from": netw["url"],
                                "to": netw["url"],
                                "status_code": netw["status"],
                                "server": netw["server"],
                                "resource_type": netw["resource_type"],
                            }
                        )
                        break

            response_data = {
                "redirects": redirects,
                "page_title": title,
                "meta_description": meta_description,
                "network_data": network_data,
                "logs": logs,
                "cookies": cookies,
                "performance_metrics": performance_metrics,
                "screenshot": screenshot_b64,
                "thumbnail": thumbnail_b64,
                "downloaded_files": downloaded_files,
                "video": video_base64,
            }

            serialized_response_data = json.dumps(response_data)
            cache.set(cache_key, serialized_response_data, expire=CACHE_EXPIRATION_SECONDS)
            
            # === DB LOGGING (SUCCESS) ===
            process_time = time.time() - start_time
            background_tasks.add_task(log_request_to_db, url, "browse", main_response_status, process_time, False, None)
            
            return JSONResponse(content=response_data)

    except Exception as e:
        # === DB LOGGING (ERROR) ===
        process_time = time.time() - start_time
        background_tasks.add_task(log_request_to_db, url, "browse", 500, process_time, False, str(e))
        
        # Re-raise the exception so FastAPI handles it
        raise e

@app.get("/screenshot", response_model=ScreenshotResponse, status_code=200)
@limiter.limit("15/minute")
async def screenshotter(
    request: Request,
    url: str,
    full_page: bool = Query(False),
    live: bool = Query(False),
    thumbnail_size: int = 450,
    quality: int = 85,
    credentials: HTTPAuthorizationCredentials = Depends(optional_auth),
):
    """
    Capture a screenshot of the specified URL, optionally skipping the cache if `live=True`.

    If the `live` parameter is set to `True`, the cache will be bypassed, and a fresh screenshot
    will be taken. Otherwise, the cached screenshot will be returned if available.

    Args:
        url (str): The URL of the page to capture a screenshot of.
        full_page (bool, optional): Whether to capture the full page or just the visible viewport. Defaults to False.
        live (bool, optional): Whether to skip the cache and take a fresh screenshot. Defaults to False.

    Returns:
        JSONResponse: A JSON response containing the base64-encoded screenshot of the page.

    Raises:
        HTTPException: If there is any issue during the Playwright interaction or screenshot capture.
    """
    cache_key = generate_cache_key(f"{url}_{full_page}")

    if not live and cache_key in cache:
        return JSONResponse(content=cache[cache_key])

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")
        screenshot = await page.screenshot(full_page=full_page)
        await browser.close()

        image = Image.open(io.BytesIO(screenshot))
        full_optimized = optimize_image(image, quality=quality)
        thumbnail_image = create_thumbnail(image, max_size=thumbnail_size)
        screenshot_b64 = base64.b64encode(full_optimized).decode("utf-8")
        thumbnail_b64 = base64.b64encode(thumbnail_image).decode("utf-8")
        images = {
            "url": page.url,
            "screenshot": screenshot_b64,
            "thumbnail": thumbnail_b64,
            "request_time": datetime.now().isoformat(),
        }

    if not live:
        cache.set(cache_key, images, expire=CACHE_EXPIRATION_SECONDS)

    return JSONResponse(content=images)

