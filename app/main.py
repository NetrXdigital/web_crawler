from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db import get_db, engine, Base
from app.models import CrawlJob, CrawledPage, JobStatus
from app.schemas import JobCreate, JobOut, PageOut
from app.tasks import run_crawl_job
from app.reports.export_xlsx import export_job_to_xlsx
import os
import time
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

app = FastAPI(title="NetrX Site Audit")

@app.on_event("startup")
def _startup():
    # Wait for DB readiness (handles container race conditions)
    for i in range(30):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            break
        except OperationalError:
            time.sleep(1)
    else:
        raise RuntimeError("Database not ready after 30 seconds")

    Base.metadata.create_all(bind=engine)

@app.post("/jobs", response_model=JobOut)
def create_job(payload: JobCreate, db: Session = Depends(get_db)):
    job = CrawlJob(
        website_url=str(payload.website_url),
        include_subdomains=payload.include_subdomains,
        render_mode=payload.render_mode,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # enqueue
    run_crawl_job.delay(job.id)
    return JobOut(**job.__dict__)

@app.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(CrawlJob, job_id)
    if not job:
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
        )
        for p in pages
    ]


@app.get("/jobs/{job_id}/export.xlsx")
def download_xlsx(job_id: int, db: Session = Depends(get_db)):
    job = db.get(CrawlJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    out_dir = "/code/exports"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"job_{job_id}.xlsx")
    export_job_to_xlsx(db, job_id, out_path)

    # FastAPI file response without extra deps:
    from fastapi.responses import FileResponse
    return FileResponse(out_path, filename=f"site_audit_{job_id}.xlsx")
