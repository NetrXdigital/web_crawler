from urllib.parse import urlparse, urlunparse, urldefrag, parse_qsl, urlencode

TRACKING_PARAMS_PREFIXES = ("utm_",)
DROP_PARAMS = {"fbclid", "gclid"}

def normalize_url(url: str) -> str:
    url, _frag = urldefrag(url)
    p = urlparse(url)

    scheme = p.scheme.lower() if p.scheme else "https"
    netloc = p.netloc.lower()

    path = p.path or "/"

    # normalize trailing slash (keep root as "/")
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    # drop tracking params
    qs = []
    for k, v in parse_qsl(p.query, keep_blank_values=True):
        lk = k.lower()
        if lk in DROP_PARAMS or any(lk.startswith(pref) for pref in TRACKING_PARAMS_PREFIXES):
            continue
        qs.append((k, v))
    query = urlencode(qs, doseq=True)

    return urlunparse((scheme, netloc, path, "", query, ""))
