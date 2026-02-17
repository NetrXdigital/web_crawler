import enum
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Boolean, Text, Enum, ForeignKey, Float, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"

class CrawlJob(Base):
    __tablename__ = "crawl_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    website_url: Mapped[str] = mapped_column(String(2048), nullable=False)

    include_subdomains: Mapped[bool] = mapped_column(Boolean, default=True)
    render_mode: Mapped[str] = mapped_column(String(32), default="hybrid")

    max_pages: Mapped[int] = mapped_column(Integer, default=5000)
    max_depth: Mapped[int] = mapped_column(Integer, default=5)
    max_minutes: Mapped[int] = mapped_column(Integer, default=60)

    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.queued)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    pages: Mapped[list["CrawledPage"]] = relationship(back_populates="job", cascade="all, delete-orphan")

class CrawledPage(Base):
    __tablename__ = "crawled_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("crawl_jobs.id", ondelete="CASCADE"), index=True)
    job: Mapped["CrawlJob"] = relationship(back_populates="pages")

    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    final_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    depth: Mapped[int] = mapped_column(Integer, default=0)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    meta_description: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    h1: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    canonical: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    robots_meta: Mapped[str | None] = mapped_column(String(512), nullable=True)

    ttfb_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    full_load_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    rendered: Mapped[bool] = mapped_column(Boolean, default=False)

    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    meta_keywords: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    h1_all: Mapped[str | None] = mapped_column(Text, nullable=True)  # store as JSON string or newline separated
    h2_all: Mapped[str | None] = mapped_column(Text, nullable=True)
    h3_all: Mapped[str | None] = mapped_column(Text, nullable=True)

Index("ix_pages_job_url", CrawledPage.job_id, CrawledPage.url, unique=True)
