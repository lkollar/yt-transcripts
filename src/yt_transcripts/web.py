"""Web UI for yt-report: submit a YouTube URL, browse the generated reports.

Usage:
    yt-report-web [--host 127.0.0.1] [--port 8765] [--out-dir reports] [--model MODEL]

There is no authentication. Keep the default host and put the UI behind a
private network or an authenticating proxy, see the README.
"""
import argparse
import itertools
import json
import queue
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import Error
from .publish import publish
from .report import make_report

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}

# Reports embed text derived from untrusted transcripts, so they get no scripts
# and an opaque origin. Links still have to open the video.
REPORT_CSP = (
    "default-src 'none'; style-src 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; img-src https://i.ytimg.com; "
    "sandbox allow-popups allow-popups-to-escape-sandbox allow-top-navigation-by-user-activation"
)

PAGE = Path(__file__).with_name("index.html").read_bytes()


class Worker:
    """Generates reports one at a time on a background thread."""

    def __init__(self, out_dir, model, cookies_from_browser):
        self.out_dir = out_dir
        self.model = model
        self.cookies_from_browser = cookies_from_browser
        self.jobs = {}
        self.ids = itertools.count(1)
        self.queue = queue.Queue()
        threading.Thread(target=self.run, daemon=True).start()

    def submit(self, url):
        job = {"id": next(self.ids), "url": url, "status": "queued", "error": None}
        self.jobs[job["id"]] = job
        self.queue.put(job)

    def run(self):
        while True:
            job = self.queue.get()
            try:
                make_report(
                    job["url"], self.out_dir,
                    cookies_from_browser=self.cookies_from_browser, model=self.model,
                    status=lambda s: job.update(status=s),
                )
                del self.jobs[job["id"]]
            except Exception as e:
                job["error"] = str(e) or type(e).__name__

    def state(self):
        reports = [json.loads(p.read_text(encoding="utf-8")) for p in Path(self.out_dir).glob("*.json")]
        # Only the URL: the update key would let any visitor overwrite the page
        for r in reports:
            if "published" in r:
                r["published"] = r["published"]["url"]
        reports.sort(key=lambda r: r["created"], reverse=True)
        return {"jobs": list(self.jobs.values()), "reports": reports}


def is_youtube_url(url):
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and parsed.hostname in YOUTUBE_HOSTS


class Handler(BaseHTTPRequestHandler):
    worker = None
    publish_lock = threading.Lock()

    def respond(self, code, body, content_type, headers=()):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def respond_json(self, code, data):
        self.respond(code, json.dumps(data).encode(), "application/json")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self.respond(200, PAGE, "text/html; charset=utf-8")
        elif path == "/api/state":
            self.respond_json(200, self.worker.state())
        elif match := re.fullmatch(r"/reports/([\w-]+)\.html", path):
            report = Path(self.worker.out_dir) / f"{match[1]}.html"
            if report.is_file():
                self.respond(200, report.read_bytes(), "text/html; charset=utf-8", [("Content-Security-Policy", REPORT_CSP)])
            else:
                self.respond_json(404, {"error": "not found"})
        else:
            self.respond_json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/jobs":
            self.submit()
        elif path == "/api/publish":
            self.publish()
        else:
            self.respond_json(404, {"error": "not found"})

    def read_field(self, name):
        """Return a string field of the JSON body, or None after an error response."""
        # Requiring JSON makes browsers preflight cross-site requests, which we
        # don't answer, so other sites can't act through a visitor's browser.
        if self.headers.get("Content-Type") != "application/json":
            self.respond_json(415, {"error": "expected application/json"})
            return None
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            return body[name].strip()
        except (ValueError, KeyError, TypeError, AttributeError):
            self.respond_json(400, {"error": "invalid request"})
            return None

    def submit(self):
        if (url := self.read_field("url")) is None:
            return
        if not is_youtube_url(url):
            return self.respond_json(400, {"error": "not a YouTube URL"})
        self.worker.submit(url)
        self.respond_json(202, {})

    def publish(self):
        if (report_id := self.read_field("id")) is None:
            return
        report = Path(self.worker.out_dir) / f"{report_id}.html"
        if not re.fullmatch(r"[\w-]+", report_id) or not report.is_file():
            return self.respond_json(404, {"error": "not found"})
        # One upload at a time, so double clicks can't create two pages
        with self.publish_lock:
            try:
                url = publish(report)
            except Error as e:
                return self.respond_json(502, {"error": str(e)})
        self.respond_json(200, {"url": url})


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--out-dir", default="reports")
    p.add_argument("--model", help="model passed to claude (default: the CLI's default)")
    p.add_argument("--cookies-from-browser", metavar="BROWSER", help="load cookies from a browser supported by yt-dlp")
    a = p.parse_args()

    Path(a.out_dir).mkdir(parents=True, exist_ok=True)
    Handler.worker = Worker(a.out_dir, a.model, a.cookies_from_browser)
    print(f"Listening on http://{a.host}:{a.port}")
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
