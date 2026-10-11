from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_TRACK = {"fbclid", "gclid", "si", "igshid", "igsh", "feature", "mc_cid", "mc_eid"}


def _host(h):
    h = (h or "").lower()
    for prefix in ("www.", "m."):
        if h.startswith(prefix):
            h = h[len(prefix):]
    return h


def classify(url):
    host = _host(urlparse(url.strip()).hostname)
    if host in ("youtube.com", "youtu.be") or host.endswith(".youtube.com"):
        return "youtube"
    if host == "instagram.com" or host.endswith(".instagram.com"):
        return "instagram"
    return "web"


def normalize_url(raw):
    """Return a usable http(s) URL, or '' if the text is not a link."""
    u = raw.strip()
    if not u:
        return ""
    if "://" not in u:
        u = "https://" + u
    try:
        p = urlparse(u)
    except ValueError:  # e.g. "http://[abc"
        return ""
    if p.scheme not in ("http", "https") or not p.hostname or "." not in p.hostname:
        return ""
    return u


def canonical(url):
    """Stable key: the same video or page maps to one key whatever the tracking params."""
    p = urlparse(url.strip())
    host = _host(p.hostname)
    path = p.path.rstrip("/")
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if k not in _TRACK and not k.startswith("utm_")]
    kind = classify(url)
    if kind == "youtube":
        vid = None
        if host == "youtu.be":
            vid = path.lstrip("/").split("/")[0]
        elif path.split("/")[1:2] in (["shorts"], ["embed"], ["live"]) and len(path.split("/")) > 2:
            vid = path.split("/")[2]
        else:
            vid = dict(q).get("v")
        if vid:
            return f"https://youtube.com/watch?v={vid}"
    if kind == "instagram":
        q = []
    return urlunparse(("https", host, path, "", urlencode(sorted(q)), ""))
