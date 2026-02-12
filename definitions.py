from pydantic import BaseModel
from typing import List , Optional , Dict 


class TimingModel(BaseModel):
    start_time: float
    domain_lookup_start: float
    domain_lookup_end: float
    connect_start: float
    secure_connection_start: float
    connect_end: float
    request_start: float
    response_start: float
    response_end: float

class CookieModel(BaseModel):
    name: str
    value: str
    domain: str
    path: str
    expires: Optional[float]
    http_only: bool
    secure: bool
    same_site: Optional[str]


class NetworkDataModel(BaseModel):
    url: str
    method: str
    headers: Dict[str, str]
    cookies: List[CookieModel]
    timing: TimingModel


class LogModel(BaseModel):
    console_message: Optional[str] = None
    javascript_error: Optional[str] = None
    warning: Optional[str] = None
    error: Optional[str] = None


class PerformanceMetricsModel(BaseModel):
    performance_timing: Dict[str, float]


class DownloadedFileModel(BaseModel):
    file_name: str
    file_content: str


class RedirectModel(BaseModel):
    step: int
    from_url: str
    to_url: str
    status_code: int
    resource_type: str
    server: Optional[Dict[str, str]] = None


lass ResponseModel(BaseModel):
    # 'network' and 'resource_type' were missing in app.py output, so we make them optional or remove them.
    # We added 'video' because app.py sends it.
    
    page_title: str
    meta_description: str
    network_data: List[NetworkDataModel]
    logs: List[LogModel]
    cookies: List[CookieModel]
    performance_metrics: PerformanceMetricsModel
    screenshot: str
    thumbnail: str
    downloaded_files: List[DownloadedFileModel]
    redirects: List[RedirectModel]
    video: str  # <--- Added this field!
    
    # Optional fields (in case we want to add them back later)
    network: Optional[str] = None
    resource_type: Optional[str] = None


class ScreenshotResponse(BaseModel):
    # Base64-encoded screenshot
    urL: str
    screenshot: str
    thumbnail: str


class MinimizeHTMLResponse(BaseModel):
    minified_html: str  # Minified HTML content


class ExtractTextResponse(BaseModel):
    text: str  # Extracts plain text from HTML content


class ReaderResponse(BaseModel):
    title: str
    content: str


class MarkdownResponse(BaseModel):
    markdown: str