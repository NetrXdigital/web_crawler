from celery import Celery
from celery.signals import worker_ready
from celery.exceptions import SoftTimeLimitExceeded
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import update
from sqlalchemy import text
import logging

from app.config import settings
from app.db import SessionLocal, engine
from app.models import CrawlJob, JobStatus
from app.crawler.orchestrator import crawl_site
from app.logging_config import configure_logging

celery_app = Celery("netrx_audit", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.conf.update(
    worker_hijack_root_logger=False,
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
)

configure_logging()
logger = logging.getLogger(__name__)


@worker_ready.connect
def mark_stale_running_jobs_failed(sender=None, **kwargs) -> None:
    """Recover jobs left in running state after worker/container interruptions."""
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE crawled_pages ADD COLUMN IF NOT EXISTS extraction_source VARCHAR(32)")
        )

    db: Session = SessionLocal()
    try:
        now = datetime.utcnow()
        stmt = (
            update(CrawlJob)
            .where(CrawlJob.status == JobStatus.running)
            .values(
                status=JobStatus.failed,
                error="Worker restarted before crawl finished",
                finished_at=now,
            )
        )
        result = db.execute(stmt)
        db.commit()
        if result.rowcount:
            logger.warning(
                "Marked stale running jobs as failed after worker startup",
                extra={"count": int(result.rowcount)},
            )
    except Exception:
        db.rollback()
        logger.exception("Failed stale job recovery during worker startup")
    finally:
        db.close()

@celery_app.task(name="run_crawl_job")
def run_crawl_job(job_id: int) -> None:
    logger.info("Worker received crawl job", extra={"job_id": job_id})
    db: Session = SessionLocal()
    try:
        job = db.get(CrawlJob, job_id)
        if not job:
            logger.warning("Crawl job not found in DB", extra={"job_id": job_id})
            return

        job.status = JobStatus.running
        job.started_at = datetime.utcnow()
        db.commit()
        logger.info("Crawl job marked running", extra={"job_id": job_id})

        crawl_site(db=db, job=job)

        job.status = JobStatus.completed
        job.finished_at = datetime.utcnow()
        db.commit()
        logger.info("Crawl job completed", extra={"job_id": job_id})
    except SoftTimeLimitExceeded:
        logger.exception("Crawl job exceeded Celery soft time limit", extra={"job_id": job_id})
        job = db.get(CrawlJob, job_id)
        if job:
            job.status = JobStatus.failed
            job.error = (
                f"Celery soft time limit exceeded "
                f"({settings.CELERY_TASK_SOFT_TIME_LIMIT}s)"
            )
            job.finished_at = datetime.utcnow()
            db.commit()
        raise
    except Exception as e:
        logger.exception("Crawl job failed", extra={"job_id": job_id})
        job = db.get(CrawlJob, job_id)
        if job:
            job.status = JobStatus.failed
            job.error = str(e)
            job.finished_at = datetime.utcnow()
            db.commit()
        raise
    finally:
        db.close()
