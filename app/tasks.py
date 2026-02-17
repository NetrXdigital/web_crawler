from celery import Celery
from datetime import datetime
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import CrawlJob, JobStatus
from app.crawler.orchestrator import crawl_site

celery_app = Celery("netrx_audit", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

@celery_app.task(name="run_crawl_job")
def run_crawl_job(job_id: int) -> None:
    db: Session = SessionLocal()
    try:
        job = db.get(CrawlJob, job_id)
        if not job:
            return

        job.status = JobStatus.running
        job.started_at = datetime.utcnow()
        db.commit()

        crawl_site(db=db, job=job)

        job.status = JobStatus.completed
        job.finished_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        job = db.get(CrawlJob, job_id)
        if job:
            job.status = JobStatus.failed
            job.error = str(e)
            job.finished_at = datetime.utcnow()
            db.commit()
        raise
    finally:
        db.close()
