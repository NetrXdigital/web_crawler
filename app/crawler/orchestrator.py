from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlparse

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.config import settings
from app.models import CrawlJob, CrawledPage
from app.crawler.normalize import normalize_url
from app.crawler.robots import load_robots, allowed_by_robots
from app.crawler.sitemap import fetch_sitemaps
from app.crawler.discovery import extract_links
from app.crawler.fetch import fetch_http, fetch_browser, should_render
from app.crawler.extract import extract_seo_fields

@dataclass(frozen=True)
class QueueItem:
    url: str
    depth: int

def is_same_site(seed_host: str, candidate_host: str, include_subdomains: bool) -> bool:
    seed_host = seed_host.lower()
    candidate_host = candidate_host.lower()
    if candidate_host == seed_host:
        return True
    if include_subdomains and candidate_host.endswith("." + seed_host):
        return True
    return False

def crawl_site(db: Session, job: CrawlJob) -> None:
    started = datetime.utcnow()
    deadline = started + timedelta(minutes=job.max_minutes)

    seed = normalize_url(job.website_url)
    seed_parsed = urlparse(seed)
    seed_host = seed_parsed.netloc

    rp = load_robots(seed, settings.USER_AGENT)

    # frontier + visited
    frontier: list[QueueItem] = [QueueItem(seed, 0)]
    visited: set[str] = set()

    # sitemap seeding
    try:
        sm_urls = fetch_sitemaps(seed, settings.USER_AGENT)
        for u in sm_urls[:2000]:  # cap sitemap intake
            nu = normalize_url(u)
            up = urlparse(nu)
            if is_same_site(seed_host, up.netloc, job.include_subdomains):
                frontier.append(QueueItem(nu, 1))
    except Exception:
        pass

    while frontier:
        if datetime.utcnow() > deadline:
            break
        if len(visited) >= job.max_pages:
            break

        item = frontier.pop(0)
        url = item.url
        depth = item.depth

        if depth > job.max_depth:
            continue

        url = normalize_url(url)
        if url in visited:
            continue

        up = urlparse(url)
        if not is_same_site(seed_host, up.netloc, job.include_subdomains):
            continue

        # robots strict
        if not allowed_by_robots(rp, settings.USER_AGENT, url):
            visited.add(url)
            continue

        # fetch
        rendered = False
        ttfb_ms = None
        full_load_ms = None
        final_url = None
        status_code = None
        html = None

        if job.render_mode in ("http", "hybrid"):
            r = fetch_http(url, settings.USER_AGENT)
            rendered = r.rendered
            ttfb_ms = r.ttfb_ms
            full_load_ms = r.full_load_ms
            final_url = r.final_url
            status_code = r.status_code
            html = r.html

        if job.render_mode in ("browser", "hybrid"):
            if job.render_mode == "browser" or should_render(html):
                br = fetch_browser(url, settings.USER_AGENT)
                rendered = True
                # if http gave ttfb, keep it; else none
                full_load_ms = br.full_load_ms
                final_url = br.final_url
                status_code = br.status_code
                html = br.html

        visited.add(url)

        # store page
        fields = extract_seo_fields(html or "")
        page = CrawledPage(
    job_id=job.id,
    url=url,
    final_url=final_url,
    depth=depth,
    status_code=status_code,
    title=fields.get("title"),
    meta_description=fields.get("meta_description"),
    meta_keywords=fields.get("meta_keywords"),
    h1=fields.get("h1"),
    h1_all=fields.get("h1_all"),
    h2_all=fields.get("h2_all"),
    h3_all=fields.get("h3_all"),
    word_count=fields.get("word_count"),
    canonical=fields.get("canonical"),
    robots_meta=fields.get("robots_meta"),
    ttfb_ms=ttfb_ms,
    full_load_ms=full_load_ms,
    rendered=rendered,
)
        try:
            db.add(page)
            db.commit()
        except Exception:
            db.rollback()

        # discover next links
        if html and status_code and 200 <= status_code < 400:
            for link in extract_links(final_url or url, html):
                nlink = normalize_url(link)
                if nlink in visited:
                    continue
                frontier.append(QueueItem(nlink, depth + 1))
