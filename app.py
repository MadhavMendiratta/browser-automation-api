from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from fastapi import FastAPI, Depends, HTTPException, Form, Query, Security, BackgroundTasks, Request
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles  # FIXED: Added for serving frontend static files
from fastapi.templating import Jinja2Templates  # FIXED: Added for Jinja2 template rendering
from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from starlette.middleware.gzip import GZipMiddleware
import playwright._impl._errors as playwright_errors
import base64
import time
import uuid
import json
import os
from datetime import datetime
from bs4 import BeautifulSoup
import htmlmin
from contextlib import asynccontextmanager

# Hamare naye database functions import karo
from database import init_db, log_request_to_db, get_request_history, get_stats, User
from auth import auth_router
from auth.dependencies import get_optional_user, get_user_from_cookie
from auth.security import verify_password, create_refresh_token, create_reset_token, decode_reset_token, hash_password, REFRESH_TOKEN_EXPIRE_DAYS, RESET_TOKEN_EXPIRE_MINUTES
from auth.schemas import _validate_username, _validate_password
from typing import Optional

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
from PIL import Image
import io
from config import setup_configurations, url_to_sha256_filename, hide_cookie_banners

# === RATE LIMITER SETUP ===
from rate_limit import limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Server start hone par DB initialize karo
    init_db(DATABASE_URL)
    yield
    # Server band hone par kuch karna ho toh yahan likho
app = FastAPI(
    title="Browser Automation API",
    description="""
    🚀 **Advanced Scraping API** built with Playwright, FastAPI, and PostgreSQL.
    
    This API allows you to automate browser tasks, capture media, and track usage.
    
    ### ✨ Key Features:
    * **🕷️ Smart Browsing:** Full JavaScript support with anti-detection & cookie blocking.
    * **📸 Media Capture:** Screenshots (Full Page), PDF, and Video recording.
    * **📊 Analytics:** Built-in dashboard for Request History & Usage Stats.
    * **🛡️ Security:** Rate Limiting to prevent abuse.
    * **🗄️ Database:** PostgreSQL integration for persistent logging.
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

# Include auth router
app.include_router(auth_router)

# FIXED: Ensure frontend directories exist before mounting
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "js"), exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "partials"), exist_ok=True)

# FIXED: Mount static files directory for CSS/JS assets
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")), name="static")

# FIXED: Initialize Jinja2 template engine
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"))


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
    current_user: Optional[User] = Depends(get_optional_user),
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
            background_tasks.add_task(log_request_to_db, url, "browse", 200, process_time, True, None, current_user.id if current_user else None)
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
            background_tasks.add_task(log_request_to_db, url, "browse", main_response_status, process_time, False, None, current_user.id if current_user else None)
            
            return JSONResponse(content=response_data)

    except Exception as e:
        # === DB LOGGING (ERROR) ===
        process_time = time.time() - start_time
        background_tasks.add_task(log_request_to_db, url, "browse", 500, process_time, False, str(e), current_user.id if current_user else None)
        
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
    current_user: Optional[User] = Depends(get_optional_user),
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

@app.get("/history", tags=["Analytics"])
@limiter.limit("60/minute")
async def history(request: Request,limit: int = 50, credentials: HTTPAuthorizationCredentials = Depends(optional_auth), current_user: Optional[User] = Depends(get_optional_user)):
    uid = current_user.id if current_user else None
    return get_request_history(limit, user_id=uid)

@app.get("/stats", tags=["Analytics"])
@limiter.limit("60/minute")
async def stats(request: Request,credentials: HTTPAuthorizationCredentials = Depends(optional_auth), current_user: Optional[User] = Depends(get_optional_user)):
    uid = current_user.id if current_user else None
    return get_stats(user_id=uid)

@app.post("/minimize", response_model=MinimizeHTMLResponse, status_code=200)
async def minimize_html(
    html: str = Form(...),
    credentials: HTTPAuthorizationCredentials = Depends(optional_auth),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """
    Minimize the given HTML content by removing unnecessary comments and whitespace.

    The HTML content provided in the `html` form field is minimized using the `htmlmin` library,
    which removes comments and extra spaces. If the minimized HTML is cached, the cached version is returned.
    Otherwise, the HTML is minimized, cached, and returned.

    Args:
        html (str): The HTML content to be minimized, provided as a form field.

    Returns:
        MinimizeHTMLResponse: A JSON response containing the minimized HTML content.

    Raises:
        HTTPException: If there are any issues during HTML minimization.

    Response schema:
        200 Successful Response:
        {
            "minified_html": "string"
        }
    """

    cache_key = generate_cache_key(html)
    if cache_key in cache:
        return JSONResponse(content={"minified_html": cache[cache_key]})

    minified_html = htmlmin.minify(html, remove_comments=True, remove_empty_space=True)
    cache.set(cache_key, minified_html, expire=CACHE_EXPIRATION_SECONDS)
    return MinimizeHTMLResponse(minified_html=minified_html)


@app.post("/extract_text", response_model=ExtractTextResponse, status_code=200)
async def extract_text_from_html(
    html: str = Form(...),
    credentials: HTTPAuthorizationCredentials = Depends(optional_auth),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """
    Extract plain text from the provided HTML content.

    The HTML content provided in the `html` form field is parsed using `BeautifulSoup`
    to extract the plain text, removing all HTML tags and formatting. If the text is cached,
    the cached version is returned. Otherwise, the plain text is extracted, cached, and returned.

    Args:
        html (str): The HTML content from which to extract plain text, provided as a form field.

    Returns:
        ExtractTextResponse: A JSON response containing the extracted plain text.

    Raises:
        HTTPException: If there are any issues during HTML parsing or text extraction.

    Response schema:
        200 Successful Response:
        {
            "text": "string"
        }
    """
    cache_key = generate_cache_key(html)

    if cache_key in cache:
        return JSONResponse(content={"text": cache[cache_key]})

    soup = BeautifulSoup(html, "html.parser")
    text_content = soup.get_text(separator=" ", strip=True)
    cache.set(cache_key, text_content, expire=CACHE_EXPIRATION_SECONDS)
    return ExtractTextResponse(text=text_content)


@app.post("/reader", response_model=ReaderResponse)
async def html_to_reader(html: str = Form(...)):
    """
    Extracts the main readable content and title from the provided HTML using the readability library.

    Parameters:
    - **html**: The raw HTML content provided via a form field.

    Returns:
    - **ReaderResponse**: A JSON object containing the extracted title and main content.
    """
    if not html:
        raise HTTPException(status_code=400, detail="No HTML content provided")

    doc = Document(html)
    reader_content = doc.summary()
    title = doc.title()

    return ReaderResponse(title=title, content=reader_content)


@app.post("/markdown", response_model=MarkdownResponse)
async def html_to_markdown(html: str = Form(...)):
    """
    Convert the provided HTML content into Markdown format.

    ### Parameters:
    - **html**: The raw HTML content provided via a form field.

    ### Returns:
    - **MarkdownResponse**: A JSON object containing the converted Markdown content.
    """
    if not html:
        raise HTTPException(status_code=400, detail="No HTML content provided")

    markdown_converter = html2text.HTML2Text()
    markdown_converter.ignore_links = False
    markdown_content = markdown_converter.handle(html)

    return MarkdownResponse(markdown=markdown_content)


@app.get("/video", response_class=FileResponse)
@limiter.limit("30/minute")
async def video(
    request: Request,
    url: str,
    browser_name: str = "chromium",
    width: int = Query(1280),
    height: int = Query(720),
):
    """
    Browse a webpage, record a video of the session, and return the video file to play in the browser.

    ### Parameters:
    - **url**: (str) The URL of the webpage to browse.
    - **browser_name**: (str) The browser to use (chromium, firefox, webkit). Defaults to "chromium".
    - **width**: (int) Video width. Defaults to 1280.
    - **height**: (int) Video height. Defaults to 720.

    ### Returns:
    - The recorded video file of the browsing session.
    """

    async with async_playwright() as p:
        browser_type = getattr(p, browser_name, None)
        if browser_type is None:
            raise HTTPException(
                status_code=400, detail=f'Browser "{browser_name}" is not supported'
            )

        video_dir = os.path.join(os.getcwd(), "videos")
        os.makedirs(video_dir, exist_ok=True)
        video_filename = url_to_sha256_filename(url)

        browser = await browser_type.launch(headless=True)
        context = await browser.new_context(
            record_video_dir=video_dir,
            record_video_size={"width": width, "height": height},
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="networkidle")
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Error navigating to the page: {str(e)}"
            )

        await context.close()
        video_path = await page.video.path()
        await browser.close()
        return FileResponse(
            video_path, media_type="video/webm", filename=video_filename
        )


# ====================================================================
# FRONTEND ROUTES — Jinja2 + HTMX Pages
# ====================================================================

# ---- Auth UI Routes ----

@app.get("/login", response_class=HTMLResponse, tags=["Auth UI"])
async def login_page(request: Request):
    """Render login form. Redirect to dashboard if already logged in."""
    user = get_user_from_cookie(request)
    if user:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("auth/login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse, tags=["Auth UI"])
@limiter.limit("5/minute")
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    """Validate credentials, set refresh cookie only, redirect to dashboard."""
    from database import get_db_session, User as DBUser
    with get_db_session() as db:
        user = db.query(DBUser).filter(DBUser.email == email).first()
        if not user or not verify_password(password, user.hashed_password):
            return templates.TemplateResponse(
                "auth/login.html", {"request": request, "error": "Invalid email or password"}
            )
        refresh_token = create_refresh_token(data={"sub": str(user.id)})

    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        samesite="lax",
        secure=False,  # set True behind HTTPS in production
        path="/",
    )
    return response


@app.get("/register", response_class=HTMLResponse, tags=["Auth UI"])
async def register_page(request: Request):
    """Render registration form."""
    user = get_user_from_cookie(request)
    if user:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("auth/register.html", {"request": request, "error": None, "success": None})


@app.post("/register", response_class=HTMLResponse, tags=["Auth UI"])
@limiter.limit("3/minute")
async def register_submit(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    """Validate inputs, create user, and redirect to login on success."""
    from database import get_db_session, User as DBUser
    from auth.security import hash_password

    # Validate password confirmation
    if password != confirm_password:
        return templates.TemplateResponse(
            "auth/register.html", {"request": request, "error": "Passwords do not match", "success": None}
        )

    # Validate username
    try:
        _validate_username(username)
    except ValueError as e:
        return templates.TemplateResponse(
            "auth/register.html", {"request": request, "error": str(e), "success": None}
        )

    # Validate password
    try:
        _validate_password(password)
    except ValueError as e:
        return templates.TemplateResponse(
            "auth/register.html", {"request": request, "error": str(e), "success": None}
        )

    with get_db_session() as db:
        if db.query(DBUser).filter(DBUser.email == email).first():
            return templates.TemplateResponse(
                "auth/register.html", {"request": request, "error": "Email already registered", "success": None}
            )
        if db.query(DBUser).filter(DBUser.username == username).first():
            return templates.TemplateResponse(
                "auth/register.html", {"request": request, "error": "Username already taken", "success": None}
            )
        db.add(DBUser(
            username=username,
            email=email,
            hashed_password=hash_password(password),
        ))

    return RedirectResponse(url="/login", status_code=302)


@app.get("/logout", tags=["Auth UI"])
async def logout(request: Request):
    """Clear refresh cookie and redirect to login."""
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(key="refresh_token", path="/", httponly=True, samesite="lax")
    return response


@app.get("/forgot-password", response_class=HTMLResponse, tags=["Auth UI"])
async def forgot_password_page(request: Request):
    """Render the forgot-password form."""
    user = get_user_from_cookie(request)
    if user:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        "auth/forgot_password.html", {"request": request, "error": None, "success": None}
    )


@app.post("/forgot-password", response_class=HTMLResponse, tags=["Auth UI"])
@limiter.limit("3/minute")
async def forgot_password_submit(request: Request, email: str = Form(...)):
    """Generate a reset token, log the link, and show a generic success message."""
    from database import get_db_session, User as DBUser
    from datetime import timedelta

    ctx = {"request": request, "error": None, "success": None}

    with get_db_session() as db:
        user = db.query(DBUser).filter(DBUser.email == email).first()
        if user:
            token = create_reset_token(data={"sub": str(user.id)})
            user.reset_token = token
            user.reset_token_expires = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)

            reset_link = f"{request.base_url}reset-password?token={token}"
            import logging
            logger = logging.getLogger(__name__)
            logger.info("PASSWORD RESET LINK (email simulation): %s", reset_link)
            print(f"\n{'='*60}")
            print(f"  PASSWORD RESET LINK (email simulation)")
            print(f"  {reset_link}")
            print(f"{'='*60}\n")

    # Always show the same message to prevent user enumeration
    ctx["success"] = "If that email is registered, a password-reset link has been sent. Check your server console."
    return templates.TemplateResponse("auth/forgot_password.html", ctx)


@app.get("/reset-password", response_class=HTMLResponse, tags=["Auth UI"])
async def reset_password_page(request: Request, token: str = Query(default="")):
    """Render the reset-password form with the token from the URL."""
    user = get_user_from_cookie(request)
    if user:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        "auth/reset_password.html",
        {"request": request, "token": token, "error": None, "success": None},
    )


@app.post("/reset-password", response_class=HTMLResponse, tags=["Auth UI"])
@limiter.limit("5/minute")
async def reset_password_submit(
    request: Request,
    token: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    """Validate the token, update the password, and show result."""
    from database import get_db_session, User as DBUser

    ctx = {"request": request, "token": token, "error": None, "success": None}

    # Validate password confirmation
    if new_password != confirm_password:
        ctx["error"] = "Passwords do not match"
        return templates.TemplateResponse("auth/reset_password.html", ctx)

    # Validate password strength
    try:
        _validate_password(new_password)
    except ValueError as e:
        ctx["error"] = str(e)
        return templates.TemplateResponse("auth/reset_password.html", ctx)

    # Decode token
    payload = decode_reset_token(token)
    if payload is None:
        ctx["error"] = "Invalid or expired reset token"
        ctx["token"] = ""
        return templates.TemplateResponse("auth/reset_password.html", ctx)

    user_id_str = payload.get("sub")
    if not user_id_str:
        ctx["error"] = "Invalid reset token"
        ctx["token"] = ""
        return templates.TemplateResponse("auth/reset_password.html", ctx)

    with get_db_session() as db:
        user = db.query(DBUser).filter(DBUser.id == int(user_id_str)).first()

        if not user or user.reset_token != token:
            ctx["error"] = "Reset token already used or invalid"
            ctx["token"] = ""
            return templates.TemplateResponse("auth/reset_password.html", ctx)

        if user.reset_token_expires is None or user.reset_token_expires < datetime.utcnow():
            ctx["error"] = "Reset token has expired"
            ctx["token"] = ""
            return templates.TemplateResponse("auth/reset_password.html", ctx)

        # Update password and invalidate token
        user.hashed_password = hash_password(new_password)
        user.reset_token = None
        user.reset_token_expires = None

    ctx["success"] = "Password has been reset successfully. You can now sign in."
    ctx["token"] = ""
    return templates.TemplateResponse("auth/reset_password.html", ctx)


# ---- Protected Frontend Pages ----

@app.get("/", response_class=HTMLResponse, tags=["Frontend"])
async def dashboard_page(request: Request):
    """Render the main Dashboard. Redirects to /login if not authenticated."""
    user = get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})


@app.get("/history-page", response_class=HTMLResponse, tags=["Frontend"])
async def history_page(request: Request):
    """Render the Request History page with the last 50 entries."""
    user = get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    history_data = get_request_history(50, user_id=user.id)
    return templates.TemplateResponse("history.html", {"request": request, "history": history_data, "user": user})


@app.get("/history-search", response_class=HTMLResponse, tags=["Frontend"])
async def history_search(request: Request, q: str = Query("")):
    """HTMX partial: filter history table rows by search query."""
    user = get_user_from_cookie(request)
    uid = user.id if user else None
    history_data = get_request_history(100, user_id=uid)
    if q.strip():
        q_lower = q.lower().strip()
        history_data = [
            h for h in history_data
            if q_lower in h.get("url", "").lower()
            or q_lower in h.get("endpoint", "").lower()
            or q_lower in str(h.get("status_code", ""))
        ]
    return templates.TemplateResponse("partials/history_rows.html", {"request": request, "history": history_data})


@app.get("/stats-page", response_class=HTMLResponse, tags=["Frontend"])
async def stats_page(request: Request):
    """Render the Analytics / Stats page with KPI cards and charts."""
    user = get_user_from_cookie(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    stats_data = get_stats(user_id=user.id)
    return templates.TemplateResponse("stats.html", {"request": request, "stats": stats_data, "user": user})


@app.post("/scrape-htmx", response_class=HTMLResponse, tags=["Frontend"])
@limiter.limit("15/minute")
async def scrape_htmx(
    request: Request,
    background_tasks: BackgroundTasks,
    url: str = Form(...),
    action: str = Form("screenshot"),
    block_cookies: bool = Form(False),
    scroll_page: bool = Form(False),
):
    """
    HTMX endpoint: Processes **only** what the chosen action requires.
      - screenshot  → capture image only (no HTML parsing)
      - browse      → full dataset (screenshot, HTML, JSON metadata)
      - extract_text → plain text only (no screenshot)
      - markdown    → markdown only (no screenshot)
    Returns a tabbed HTML partial (result_card.html) for Alpine.js tab switching.
    """
    start_time = time.time()
    result = {}
    user = get_user_from_cookie(request)
    uid = user.id if user else None

    VALID_ACTIONS = {"screenshot", "browse", "extract_text", "markdown"}
    if action not in VALID_ACTIONS:
        action = "screenshot"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            # Navigate
            nav_response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            status_code = nav_response.status if nav_response else 0

            # Optional: close cookie banners
            if block_cookies:
                try:
                    await hide_cookie_banners(page)
                except Exception:
                    pass

            # Wait for network to settle
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except PlaywrightTimeoutError:
                pass

            # Optional: scroll to bottom
            if scroll_page:
                try:
                    await smooth_scroll(page, max_duration=10)
                except Exception:
                    pass

            title = await page.title() or "Untitled"

            # ----- Action-specific processing -----
            screenshot_b64 = ""
            thumbnail_b64 = ""
            raw_html = ""
            primary_data = ""
            json_data = ""

            if action == "screenshot":
                # Only capture image — skip all HTML processing
                screenshot_bytes = await page.screenshot(full_page=True)
                image = Image.open(io.BytesIO(screenshot_bytes))
                optimized = optimize_image(image, quality=85)
                thumbnail_img = create_thumbnail(image, max_size=450)
                screenshot_b64 = base64.b64encode(optimized).decode("utf-8")
                thumbnail_b64 = base64.b64encode(thumbnail_img).decode("utf-8")

            elif action == "browse":
                # Full dataset: screenshot + HTML + JSON metadata
                screenshot_bytes = await page.screenshot(full_page=True)
                image = Image.open(io.BytesIO(screenshot_bytes))
                optimized = optimize_image(image, quality=85)
                thumbnail_img = create_thumbnail(image, max_size=450)
                screenshot_b64 = base64.b64encode(optimized).decode("utf-8")
                thumbnail_b64 = base64.b64encode(thumbnail_img).decode("utf-8")

                raw_html = await page.content()

                meta_description = ""
                try:
                    meta_el = await page.locator("meta[name='description']").get_attribute("content")
                    meta_description = meta_el or ""
                except Exception:
                    pass

                cookies = await context.cookies()

                json_metadata = {
                    "url": url,
                    "page_url": page.url,
                    "action": action,
                    "status_code": status_code,
                    "title": title,
                    "meta_description": meta_description,
                    "cookies_count": len(cookies),
                    "cookies": [
                        {"name": c["name"], "domain": c["domain"], "secure": c["secure"]}
                        for c in cookies
                    ],
                }
                json_data = json.dumps(json_metadata, indent=2)

            elif action == "extract_text":
                # Only extract text — no screenshot
                raw_html = await page.content()
                soup = BeautifulSoup(raw_html, "html.parser")
                primary_data = soup.get_text(separator="\n", strip=True)
                raw_html = ""  # not needed in result

            elif action == "markdown":
                # Only convert to markdown — no screenshot
                page_html = await page.content()
                md_converter = html2text.HTML2Text()
                md_converter.ignore_links = False
                primary_data = md_converter.handle(page_html)

            await context.close()
            await browser.close()

        process_time = time.time() - start_time

        result = {
            "type": action,
            "data": primary_data,
            "screenshot": screenshot_b64,
            "thumbnail": thumbnail_b64,
            "raw_html": raw_html,
            "json_data": json_data,
            "title": title,
            "status_code": status_code,
            "response_time": round(process_time, 2),
            "url": url,
            "success": True,
        }

        # Log to DB in background
        background_tasks.add_task(
            log_request_to_db, url, action, status_code, process_time, False, None, uid
        )

        response = templates.TemplateResponse(
            "partials/result_card.html", {"request": request, "result": result}
        )
        response.headers["HX-Trigger"] = json.dumps({
            "showToast": {"message": f"Scraping completed — {title[:40]}", "type": "success"}
        })
        return response

    except Exception as e:
        process_time = time.time() - start_time
        result = {
            "type": "error",
            "data": str(e),
            "screenshot": "",
            "thumbnail": "",
            "raw_html": "",
            "json_data": json.dumps({"error": str(e)}, indent=2),
            "success": False,
            "response_time": round(process_time, 2),
            "url": url,
            "status_code": 500,
            "title": "Error",
        }
        background_tasks.add_task(
            log_request_to_db, url, action, 500, process_time, False, str(e), uid
        )

        response = templates.TemplateResponse(
            "partials/result_card.html", {"request": request, "result": result}
        )
        response.headers["HX-Trigger"] = json.dumps({
            "showToast": {"message": f"Scraping failed: {str(e)[:80]}", "type": "error"}
        })
        return response


# ====================================================================
# HTMX COMPONENT ENDPOINTS
# ====================================================================

@app.get("/components/recent-activity", response_class=HTMLResponse, tags=["Frontend"])
async def recent_activity_component(request: Request):
    """HTMX partial: Returns the last 5 requests for the current user."""
    user = get_user_from_cookie(request)
    uid = user.id if user else None
    history_data = get_request_history(5, user_id=uid)
    return templates.TemplateResponse(
        "partials/recent_activity.html", {"request": request, "items": history_data}
    )


@app.get("/api/health", tags=["System"])
async def health_check():
    """Simple health check endpoint for the server status indicator."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}
