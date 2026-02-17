from sqlalchemy.orm import Session
from sqlalchemy import select
from openpyxl import Workbook
from app.models import CrawledPage

def export_job_to_xlsx(db: Session, job_id: int, out_path: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Pages"

    headers = [
        "url","final_url","depth","status_code",
        "title","meta_description","meta_keywords",
        "h1","h1_all","h2_all","h3_all",
        "word_count","canonical","robots_meta",
        "ttfb_ms","full_load_ms","rendered"
    ]
    ws.append(headers)

    stmt = select(CrawledPage).where(CrawledPage.job_id == job_id).order_by(CrawledPage.depth.asc(), CrawledPage.url.asc())
    for p in db.execute(stmt).scalars():
        ws.append([
            p.url, p.final_url, p.depth, p.status_code,
            p.title, p.meta_description, p.h1, p.word_count,
            p.canonical, p.robots_meta,
            p.ttfb_ms, p.full_load_ms, p.rendered,
            p.meta_keywords, p.h1, p.h1_all, p.h2_all, p.h3_all
        ])

    wb.save(out_path)
