from bs4 import BeautifulSoup

def _get_meta_content(soup: BeautifulSoup, name: str) -> str | None:
    tag = soup.find("meta", attrs={"name": name})
    if tag and tag.get("content"):
        return tag["content"].strip()
    return None

def _extract_headings(soup: BeautifulSoup, tag_name: str) -> list[str]:
    out = []
    for t in soup.find_all(tag_name):
        txt = t.get_text(" ", strip=True)
        if txt:
            out.append(txt)
    # de-dupe preserving order
    seen = set()
    dedup = []
    for x in out:
        if x not in seen:
            seen.add(x)
            dedup.append(x)
    return dedup

def extract_seo_fields(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    title = soup.title.get_text(strip=True) if soup.title else None

    meta_description = _get_meta_content(soup, "description")
    meta_keywords = _get_meta_content(soup, "keywords")
    robots_meta = _get_meta_content(soup, "robots")

    canonical = None
    can = soup.find("link", attrs={"rel": "canonical"})
    if can and can.get("href"):
        canonical = can["href"].strip()

    # Headings (all)
    h1_list = _extract_headings(soup, "h1")
    h2_list = _extract_headings(soup, "h2")
    h3_list = _extract_headings(soup, "h3")

    # Backwards-compatible single h1 (first)
    h1 = h1_list[0] if h1_list else None

    # visible text word count
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    word_count = len([w for w in text.split() if w])

    return {
        "title": title,
        "meta_description": meta_description,
        "meta_keywords": meta_keywords,
        "robots_meta": robots_meta,
        "canonical": canonical,
        "h1": h1,
        "h1_all": "\n".join(h1_list) if h1_list else None,
        "h2_all": "\n".join(h2_list) if h2_list else None,
        "h3_all": "\n".join(h3_list) if h3_list else None,
        "word_count": word_count,
    }
