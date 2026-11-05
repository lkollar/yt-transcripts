#!/usr/bin/env python3
"""Web UI for yt_report.py: submit a YouTube URL, browse the generated reports.

Usage:
    uv run web.py [--host 127.0.0.1] [--port 8765] [--out-dir reports] [--model MODEL]

There is no authentication. Keep the default host and expose it to your tailnet
with `tailscale serve`, see the README.
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

from yt_report import make_report

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}

# Reports embed text derived from untrusted transcripts, so they get no scripts
# and an opaque origin. Links still have to open the video.
REPORT_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; img-src https://i.ytimg.com; "
    "sandbox allow-popups allow-popups-to-escape-sandbox allow-top-navigation-by-user-activation"
)

PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Video reports</title>
<style>
:root { color-scheme: light dark; --fg: #1c1c1e; --muted: #6e6e73; --line: #e2e2e6; --bg: #fafafa; --card: #fff; --accent: #2f5fd0; --bad: #c0362c; }
@media (prefers-color-scheme: dark) { :root { --fg: #ececee; --muted: #9a9aa2; --line: #333338; --bg: #161618; --card: #1f1f22; --accent: #8aa9f5; --bad: #f08a80; } }
* { box-sizing: border-box; }
body { margin: 0 auto; max-width: 720px; padding: 2rem 1rem 4rem; background: var(--bg); color: var(--fg); font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
h1 { font-size: 1.5rem; margin: 0 0 1rem; }
h2 { font-size: .8rem; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); margin: 2rem 0 .5rem; }
form { display: flex; gap: .5rem; }
input { flex: 1; min-width: 0; padding: .6rem .75rem; font: inherit; color: inherit; background: var(--card); border: 1px solid var(--line); border-radius: 8px; }
button { padding: .6rem 1rem; font: inherit; font-weight: 600; color: #fff; background: #2f5fd0; border: 0; border-radius: 8px; cursor: pointer; }
ul { list-style: none; margin: 0; padding: 0; }
li { padding: .75rem 0; border-bottom: 1px solid var(--line); overflow-wrap: anywhere; }
a { color: var(--accent); text-decoration: none; font-weight: 600; }
a:hover { text-decoration: underline; }
.meta { color: var(--muted); font-size: .875rem; }
.error { color: var(--bad); font-size: .875rem; white-space: pre-wrap; }
</style>
</head>
<body>
<h1>Video reports</h1>
<form id="form">
  <input id="url" type="url" required autofocus placeholder="YouTube URL" aria-label="YouTube URL">
  <button>Generate</button>
</form>
<p id="form-error" class="error" role="alert"></p>
<section id="jobs-section" hidden><h2>Jobs</h2><ul id="jobs"></ul></section>
<section id="reports-section" hidden><h2>Reports</h2><ul id="reports"></ul></section>
<script>
const $ = id => document.getElementById(id);
const el = (tag, className, text) => {
  const e = document.createElement(tag);
  if (className) e.className = className;
  if (text != null) e.textContent = text;
  return e;
};
const duration = s => {
  if (!s) return "";
  const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60);
  return h ? `${h}h ${m}m` : `${m}m`;
};

function render(state) {
  const jobs = state.jobs.map(j => {
    const li = el("li");
    li.append(el("div", null, j.url));
    li.append(j.error ? el("div", "error", j.error) : el("div", "meta", j.status + "\\u2026"));
    return li;
  });
  $("jobs").replaceChildren(...jobs);
  $("jobs-section").hidden = !jobs.length;

  const reports = state.reports.map(r => {
    const li = el("li"), a = el("a", null, r.title || r.id);
    a.href = `reports/${r.id}.html`;
    li.append(a, el("div", "meta", [r.channel, duration(r.duration), new Date(r.created * 1000).toLocaleDateString()].filter(Boolean).join(" \\u00b7 ")));
    return li;
  });
  $("reports").replaceChildren(...reports);
  $("reports-section").hidden = !reports.length;
}

async function refresh() {
  try {
    const state = await (await fetch("api/state")).json();
    render(state);
    return state.jobs.some(j => !j.error);
  } catch { return true; }
}

let polling = false;
async function poll() {
  if (polling) return;
  polling = true;
  while (await refresh()) await new Promise(r => setTimeout(r, 2000));
  polling = false;
}

$("form").addEventListener("submit", async e => {
  e.preventDefault();
  $("form-error").textContent = "";
  const res = await fetch("api/jobs", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({url: $("url").value}),
  });
  if (res.ok) { $("url").value = ""; poll(); }
  else $("form-error").textContent = (await res.json()).error;
});

poll();
</script>
</body>
</html>
"""


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
            # fetch and make_report report failures with SystemExit
            except (Exception, SystemExit) as e:
                job["error"] = str(e) or type(e).__name__

    def state(self):
        reports = [json.loads(p.read_text(encoding="utf-8")) for p in Path(self.out_dir).glob("*.json")]
        reports.sort(key=lambda r: r["created"], reverse=True)
        return {"jobs": list(self.jobs.values()), "reports": reports}


def is_youtube_url(url):
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and parsed.hostname in YOUTUBE_HOSTS


class Handler(BaseHTTPRequestHandler):
    worker = None

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
            self.respond(200, PAGE.encode(), "text/html; charset=utf-8")
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
        if urlparse(self.path).path != "/api/jobs":
            return self.respond_json(404, {"error": "not found"})
        # Requiring JSON makes browsers preflight cross-site requests, which we
        # don't answer, so other sites can't start jobs through a visitor's browser.
        if self.headers.get("Content-Type") != "application/json":
            return self.respond_json(415, {"error": "expected application/json"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            url = body["url"].strip()
        except (ValueError, KeyError, TypeError, AttributeError):
            return self.respond_json(400, {"error": "invalid request"})
        if not is_youtube_url(url):
            return self.respond_json(400, {"error": "not a YouTube URL"})
        self.worker.submit(url)
        self.respond_json(202, {})


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
