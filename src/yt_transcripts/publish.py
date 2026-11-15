"""Share reports as public pages on ht-ml.app."""
import json
import urllib.error
import urllib.request

from . import Error
from .report import read_meta, write_meta

API = "https://api.ht-ml.app/v1/sites"


def publish(path):
    """Upload a report to ht-ml.app, or update its earlier upload. Returns the public URL.

    The page is public. The update key is stored in the report's metadata, as
    ht-ml.app can't recover it.
    """
    meta = read_meta(path) or {}
    published = meta.get("published")
    body = json.dumps({"html_content": path.read_text(encoding="utf-8")}).encode()
    headers = {"Content-Type": "application/json"}
    if published:
        url, method = f"{API}/{published['site_id']}", "PUT"
        headers["Authorization"] = f"Bearer {published['update_key']}"
    else:
        url, method = API, "POST"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, body, headers, method=method), timeout=60) as r:
            site = json.load(r)
    except urllib.error.HTTPError as e:
        try:
            message = json.load(e)["message"]
        except (ValueError, KeyError, TypeError):
            message = e.reason
        raise Error(f"publishing failed: HTTP {e.code}: {message}")
    except urllib.error.URLError as e:
        raise Error(f"publishing failed: {e.reason}")
    if not published:
        meta["published"] = {k: site[k] for k in ("site_id", "url", "update_key")}
        write_meta(path, meta)
    return meta["published"]["url"]
