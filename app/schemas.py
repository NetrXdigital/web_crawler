from datetime import datetime
from pydantic import BaseModel, AnyHttpUrl, Field
from typing import Literal, Optional

RenderMode = Literal["hybrid", "http", "browser"]

class JobCreate(BaseModel):
    website_url: AnyHttpUrl
    include_subdomains: bool = True
    render_mode: RenderMode = "hybrid"

class JobOut(BaseModel):
    id: int
    website_url: str
    status: str
    error: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

class PageOut(BaseModel):
    url: str
    final_url: Optional[str] = None
    depth: int
    status_code: Optional[int] = None

    title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None

    h1: Optional[str] = None
    h1_all: Optional[str] = None
    h2_all: Optional[str] = None
    h3_all: Optional[str] = None

    word_count: Optional[int] = None
    canonical: Optional[str] = None
    robots_meta: Optional[str] = None
    ttfb_ms: Optional[float] = None
    full_load_ms: Optional[float] = None
    rendered: bool
    extraction_source: Optional[str] = None
