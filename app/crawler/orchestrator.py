from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import deque
from urllib.parse import urlparse
import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.models import CrawlJob, CrawledPage
from app.crawler.normalize import normalize_url
from app.crawler.robots import load_robots, allowed_by_robots
from app.crawler.sitemap import fetch_sitemaps
from app.crawler.discovery import extract_links
from app.crawler.fetch import fetch_http, fetch_browser, should_render
from app.crawler.extract import extract_seo_fields

logger = logging.getLogger(__name__)

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

    logger.info(
        "Starting crawl",
        extra={
            "job_id": job.id,
            "seed": seed,
            "max_pages": job.max_pages,
            "max_depth": job.max_depth,
            "max_minutes": job.max_minutes,
            "render_mode": job.render_mode,
            "include_subdomains": job.include_subdomains,
        },
    )

    rp = load_robots(seed, settings.USER_AGENT)

    # frontier + visited
    frontier: deque[QueueItem] = deque([QueueItem(seed, 0)])
    enqueued: set[str] = {seed}
    visited: set[str] = set()

    # sitemap seeding
    try:
        sm_urls = fetch_sitemaps(seed, settings.USER_AGENT)
        sitemap_added = 0
        for u in sm_urls[:2000]:  # cap sitemap intake
            nu = normalize_url(u)
            up = urlparse(nu)
            if is_same_site(seed_host, up.netloc, job.include_subdomains):
                if nu not in visited and nu not in enqueued:
                    frontier.append(QueueItem(nu, 1))
                    enqueued.add(nu)
                    sitemap_added += 1
        logger.info(
            "Seeded URLs from sitemap",
            extra={"job_id": job.id, "sitemap_urls_added": sitemap_added},
        )
    except Exception:
        logger.exception("Failed to fetch or parse sitemap", extra={"job_id": job.id})

    while frontier:
        if datetime.utcnow() > deadline:
            logger.warning("Stopping crawl due to timeout", extra={"job_id": job.id})
            break
        if len(visited) >= job.max_pages:
            logger.warning("Stopping crawl due to max pages", extra={"job_id": job.id})
            break

        item = frontier.popleft()
        url = item.url
        depth = item.depth

        if depth > job.max_depth:
            logger.debug("Skipping URL over max depth", extra={"job_id": job.id, "url": url, "depth": depth})
            continue

        url = normalize_url(url)
        enqueued.discard(url)
        if url in visited:
            logger.debug("Skipping already visited URL", extra={"job_id": job.id, "url": url})
            continue

        up = urlparse(url)
        if not is_same_site(seed_host, up.netloc, job.include_subdomains):
            logger.debug("Skipping offsite URL", extra={"job_id": job.id, "url": url})
            continue

        # robots strict
        if not allowed_by_robots(rp, settings.USER_AGENT, url):
            visited.add(url)
            logger.info("Skipping URL blocked by robots.txt", extra={"job_id": job.id, "url": url})
            continue

        logger.info("Fetching URL", extra={"job_id": job.id, "url": url, "depth": depth})

        # fetch
        rendered = False
        ttfb_ms = None
        full_load_ms = None
        final_url = None
        status_code = None
        html = None

        if job.render_mode in ("http", "hybrid"):
            try:
                r = fetch_http(url, settings.USER_AGENT)
                rendered = r.rendered
                ttfb_ms = r.ttfb_ms
                full_load_ms = r.full_load_ms
                final_url = r.final_url
                status_code = r.status_code
                html = r.html
                logger.debug(
                    "HTTP fetch complete",
                    extra={
                        "job_id": job.id,
                        "url": url,
                        "status_code": status_code,
                        "ttfb_ms": ttfb_ms,
                        "full_load_ms": full_load_ms,
                        "final_url": final_url,
                    },
                )
            except Exception:
                logger.exception("HTTP fetch failed", extra={"job_id": job.id, "url": url})

        if job.render_mode in ("browser", "hybrid"):
            if job.render_mode == "browser" or should_render(html):
                try:
                    br = fetch_browser(url, settings.USER_AGENT, timeout_ms=settings.BROWSER_TIMEOUT_MS)
                    rendered = True
                    # if http gave ttfb, keep it; else none
                    full_load_ms = br.full_load_ms
                    final_url = br.final_url
                    status_code = br.status_code
                    html = br.html
                    logger.debug(
                        "Browser fetch complete",
                        extra={
                            "job_id": job.id,
                            "url": url,
                            "status_code": status_code,
                            "full_load_ms": full_load_ms,
                            "final_url": final_url,
                        },
                    )
                except Exception:
                    logger.warning(
                        "Browser fetch failed; continuing with available data",
                        extra={"job_id": job.id, "url": url},
                        exc_info=True,
                    )

        visited.add(url)

        # store page
        try:
            fields = extract_seo_fields(html or "")
        except Exception:
            logger.exception("SEO extraction failed", extra={"job_id": job.id, "url": url})
            fields = {}
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
            logger.info(
                "Stored crawled page",
                extra={
                    "job_id": job.id,
                    "url": url,
                    "depth": depth,
                    "status_code": status_code,
                    "rendered": rendered,
                    "word_count": fields.get("word_count"),
                },
            )
        except Exception:
            db.rollback()
            logger.exception("Failed to persist crawled page", extra={"job_id": job.id, "url": url})

        # discover next links
        if html and status_code and 200 <= status_code < 400:
            try:
                discovered = 0
                for link in extract_links(final_url or url, html):
                    nlink = normalize_url(link)
                    if nlink in visited or nlink in enqueued:
                        continue
                    frontier.append(QueueItem(nlink, depth + 1))
                    enqueued.add(nlink)
                    discovered += 1
                logger.debug(
                    "Discovered links from page",
                    extra={"job_id": job.id, "url": url, "discovered_links": discovered},
                )
            except Exception:
                logger.exception("Link discovery failed", extra={"job_id": job.id, "url": url})

    logger.info(
        "Crawl finished",
        extra={"job_id": job.id, "visited_count": len(visited), "frontier_remaining": len(frontier)},
    )
