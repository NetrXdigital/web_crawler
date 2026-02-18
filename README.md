# NetrX Web Crawler

This service crawls a website, extracts SEO/content fields per page, stores results in Postgres, and exports reports as XLSX.

## Components

- `api` (FastAPI): accepts crawl jobs and exposes job/page/report endpoints.
- `worker` (Celery): executes crawl jobs asynchronously.
- `redis`: Celery broker/backend.
- `db` (Postgres): stores `crawl_jobs` and `crawled_pages`.

## What Celery Does

The worker has one crawl task:

- `run_crawl_job(job_id)`:
  - loads the job from DB
  - marks status `running`
  - calls crawler orchestrator (`crawl_site`)
  - marks status `completed` on success
  - marks status `failed` with error on unhandled failure

On worker startup, a recovery hook runs:

- any old jobs stuck in `running` (for example after container restart) are marked `failed` with error:
  - `"Worker restarted before crawl finished"`

Configured hard time limit:

- `CELERY_TASK_TIME_LIMIT` (seconds) from `.env`
- default is `3600` (1 hour)

## How Each URL Is Processed

For every URL in the crawl queue:

1. Normalize URL and enforce scope (same site/subdomains setting).
2. Enforce robots.txt policy.
3. Fetch content:
   - HTTP fetch first for `http`/`hybrid`.
   - Browser fetch for `browser`, or in `hybrid` when `should_render(html)` indicates JS-heavy page.
4. Extract fields from HTML:
   - title, meta description/keywords, canonical, robots meta
   - headings (`h1`, `h1_all`, `h2_all`, `h3_all`)
   - word count
5. Persist one `crawled_pages` row in Postgres.
6. Discover links from HTML and enqueue unseen links.

Resilience behavior:

- Per-URL errors are logged and crawl continues.
- Browser timeout/failure falls back to available HTTP data when possible.
- Queue de-dup avoids repeatedly enqueuing the same URL.

## Timeouts and Limits

From current config:

- `MAX_PAGES=5000`
- `MAX_DEPTH=5`
- `MAX_MINUTES=60` (job-level crawl deadline)
- `CELERY_TASK_TIME_LIMIT=3600` seconds (hard kill by Celery)
- `BROWSER_TIMEOUT_MS=15000` (Playwright per URL)
- HTTP fetch timeout is 20 seconds per URL (code default).

## Run Guide

### 1) Start stack

```bash
cd /Users/anmol.dhar/netrX/netrx_web_crawler/web_crawler
docker compose up -d
docker compose ps
```

### 2) Submit crawl job

```bash
docker compose exec -T api curl -s -X POST "http://127.0.0.1:8000/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "website_url": "https://www.instanthub.in/",
    "include_subdomains": true,
    "render_mode": "hybrid"
  }'
```

The response contains `id` (job id).

### 3) Track job

```bash
docker compose exec -T api curl -s "http://127.0.0.1:8000/jobs/<JOB_ID>"
```

### 4) Get pages

```bash
docker compose exec -T api curl -s "http://127.0.0.1:8000/jobs/<JOB_ID>/pages"
```

### 5) Export Excel report

```bash
docker compose exec -T api curl -s -L "http://127.0.0.1:8000/jobs/<JOB_ID>/export.xlsx" -o /code/site_audit_<JOB_ID>.xlsx
```

## Logs and Debugging

```bash
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f api worker
```

Useful checks:

- worker not processing:
  - `docker compose ps`
- jobs look stuck in `running`:
  - restart worker; stale running jobs are auto-marked failed on startup
  - `docker compose restart worker`

## Common Render Modes

- `hybrid`: fastest stable default (HTTP first, browser fallback).
- `http`: no browser, best for speed/stability.
- `browser`: full browser for every URL, slowest/heaviest.
