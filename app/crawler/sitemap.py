from urllib.parse import urljoin
import httpx
from bs4 import BeautifulSoup

def guess_sitemap_urls(root_url: str) -> list[str]:
    # Common locations
    base = root_url.rstrip("/") + "/"
    return [
        urljoin(base, "sitemap.xml"),
        urljoin(base, "sitemap_index.xml"),
        urljoin(base, "sitemap-index.xml"),
    ]

def parse_sitemap_xml(xml_text: str) -> list[str]:
    soup = BeautifulSoup(xml_text, "xml")
    locs = [loc.get_text(strip=True) for loc in soup.find_all("loc")]
    return [u for u in locs if u]

def fetch_sitemaps(root_url: str, user_agent: str, timeout_s: float = 15.0) -> list[str]:
    urls: list[str] = []
    with httpx.Client(follow_redirects=True, timeout=timeout_s, headers={"User-Agent": user_agent}) as client:
        for sm_url in guess_sitemap_urls(root_url):
            try:
                r = client.get(sm_url)
                if r.status_code >= 400 or not r.text:
                    continue
                locs = parse_sitemap_xml(r.text)

                # If sitemap index, fetch children
                if any(sm.endswith(".xml") for sm in locs) and "<sitemapindex" in r.text.lower():
                    for child in locs[:200]:  # safety cap
                        try:
                            rr = client.get(child)
                            if rr.status_code < 400 and rr.text:
                                urls.extend(parse_sitemap_xml(rr.text))
                        except Exception:
                            continue
                else:
                    urls.extend(locs)
            except Exception:
                continue

    # De-dupe preserving order
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out
