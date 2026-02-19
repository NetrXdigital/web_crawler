from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db import get_db, engine, Base
from app.models import CrawlJob, CrawledPage, JobStatus
from app.schemas import JobCreate, JobOut, PageOut
from app.tasks import run_crawl_job
from app.reports.export_xlsx import export_job_to_xlsx
from app.logging_config import configure_logging
from app.config import settings
import os
import time
import logging
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="NetrX Site Audit")

@app.on_event("startup")
def _startup():
    # Wait for DB readiness (handles container race conditions)
    logger.info("API startup initiated")
    for i in range(30):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connection ready")
            break
        except OperationalError:
            logger.warning("Database not ready yet", extra={"attempt": i + 1})
            time.sleep(1)
    else:
        logger.error("Database not ready after max retries")
        raise RuntimeError("Database not ready after 30 seconds")

    Base.metadata.create_all(bind=engine)
    # Keep schema backwards-compatible for existing DB volumes without migrations.
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE crawled_pages ADD COLUMN IF NOT EXISTS extraction_source VARCHAR(32)")
        )
    logger.info("Database metadata ensured")

@app.post("/jobs", response_model=JobOut)
def create_job(payload: JobCreate, db: Session = Depends(get_db)):
    job = CrawlJob(
        website_url=str(payload.website_url),
        include_subdomains=payload.include_subdomains,
        render_mode=payload.render_mode,
        max_pages=settings.MAX_PAGES,
        max_depth=settings.MAX_DEPTH,
        max_minutes=settings.MAX_MINUTES,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info("Created crawl job", extra={"job_id": job.id, "url": job.website_url})

    # enqueue
    run_crawl_job.delay(job.id)
    logger.info("Enqueued crawl job", extra={"job_id": job.id})
    return JobOut(**job.__dict__)

@app.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(CrawlJob, job_id)
    if not job:
        logger.warning("Job lookup failed", extra={"job_id": job_id})
        raise HTTPException(404, "Job not found")
    return JobOut(**job.__dict__)

@app.get("/jobs/{job_id}/pages", response_model=list[PageOut])
def list_pages(job_id: int, db: Session = Depends(get_db)):
    stmt = (
        select(CrawledPage)
        .where(CrawledPage.job_id == job_id)
        .order_by(CrawledPage.depth.asc(), CrawledPage.url.asc())
    )
    pages = db.execute(stmt).scalars().all()
    logger.info("Listing crawled pages", extra={"job_id": job_id, "page_count": len(pages)})

    return [
        PageOut(
            url=p.url,
            final_url=p.final_url,
            depth=p.depth,
            status_code=p.status_code,

            title=p.title,
            meta_description=p.meta_description,
            meta_keywords=p.meta_keywords,

            h1=p.h1,
            h1_all=p.h1_all,
            h2_all=p.h2_all,
            h3_all=p.h3_all,

            word_count=p.word_count,
            canonical=p.canonical,
            robots_meta=p.robots_meta,

            ttfb_ms=p.ttfb_ms,
            full_load_ms=p.full_load_ms,
            rendered=p.rendered,
            extraction_source=p.extraction_source,
        )
        for p in pages
    ]


@app.get("/jobs/{job_id}/export.xlsx")
def download_xlsx(job_id: int, db: Session = Depends(get_db)):
    job = db.get(CrawlJob, job_id)
    if not job:
        logger.warning("Export failed, job not found", extra={"job_id": job_id})
        raise HTTPException(404, "Job not found")

    out_dir = "/code/exports"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"job_{job_id}.xlsx")
    export_job_to_xlsx(db, job_id, out_path)
    logger.info("Exported xlsx report", extra={"job_id": job_id, "path": out_path})

    # FastAPI file response without extra deps:
    from fastapi.responses import FileResponse
    return FileResponse(out_path, filename=f"site_audit_{job_id}.xlsx")
