from dataclasses import dataclass
import time
import httpx
from playwright.sync_api import sync_playwright

@dataclass
class FetchResult:
    final_url: str | None
    status_code: int | None
    html: str | None
    ttfb_ms: float | None
    full_load_ms: float | None
    rendered: bool

def fetch_http(url: str, user_agent: str, timeout_s: float = 20.0) -> FetchResult:
    headers = {"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml"}
    with httpx.Client(follow_redirects=True, timeout=timeout_s, headers=headers) as client:
        start = time.perf_counter()
        r = client.get(url)
        # crude but effective: time to first response completion ~ not perfect TTFB
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        html = r.text if "text/html" in r.headers.get("content-type", "").lower() else None
        return FetchResult(
            final_url=str(r.url),
            status_code=r.status_code,
            html=html,
            ttfb_ms=elapsed_ms,
            full_load_ms=None,
            rendered=False,
        )

def fetch_browser(url: str, user_agent: str, timeout_ms: int = 15000) -> FetchResult:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=user_agent)
        page = ctx.new_page()

        start = time.perf_counter()
        # "domcontentloaded" is usually enough for SEO extraction and avoids waiting
        # on slow third-party assets that can make "load" appear hung.
        resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        full_load_ms = (time.perf_counter() - start) * 1000.0

        html = page.content()
        final_url = page.url
        status_code = resp.status if resp else None

        ctx.close()
        browser.close()

        return FetchResult(
            final_url=final_url,
            status_code=status_code,
            html=html,
            ttfb_ms=None,
            full_load_ms=full_load_ms,
            rendered=True,
        )

def should_render(html: str | None) -> bool:
    if not html:
        return True
    low = html.lower()
    # common SPA signals
    if '<div id="root"' in low or '<div id="__next"' in low:
        return True
    # too little content often means JS
    if len(html) < 1500:
        return True
    return False
