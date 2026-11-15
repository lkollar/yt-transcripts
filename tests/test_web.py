import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from yt_transcripts import publish as publish_module
from yt_transcripts import web


@pytest.fixture
def server(tmp_path, monkeypatch):
    (tmp_path / "abc.html").write_text("<html></html>")
    (tmp_path / "abc.json").write_text(json.dumps({"id": "abc", "created": 1}))
    uploads = []

    def fake_publish(path):
        uploads.append(path.name)
        meta = json.loads(path.with_suffix(".json").read_text())
        meta["published"] = {"site_id": "s", "url": "https://s.ht-ml.app/", "update_key": "secret"}
        path.with_suffix(".json").write_text(json.dumps(meta))
        return "https://s.ht-ml.app/"

    monkeypatch.setattr(web, "publish", fake_publish)
    monkeypatch.setattr(web, "send", lambda path, **config: uploads.append(("kindle", path.name, config["to"])))
    monkeypatch.setattr(web.Handler, "worker", web.Worker(str(tmp_path), None, None))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", uploads
    httpd.shutdown()


def request(url, data=None, content_type="application/json"):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, body, {"Content-Type": content_type} if body else {})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def test_publish_hides_update_key(server):
    base, uploads = server
    assert request(base + "/api/publish", {"id": "abc"}) == (200, {"url": "https://s.ht-ml.app/"})
    assert uploads == ["abc.html"]
    _, state = request(base + "/api/state")
    assert state["reports"][0]["published"] == "https://s.ht-ml.app/"
    assert "secret" not in json.dumps(state)


@pytest.mark.parametrize("report_id", ["../abc", "missing"])
def test_publish_rejects_unknown_reports(server, report_id):
    base, uploads = server
    assert request(base + "/api/publish", {"id": report_id})[0] == 404
    assert uploads == []


def test_kindle_hidden_unless_configured(server):
    base, uploads = server
    assert request(base + "/api/state")[1]["kindle"] is False
    assert request(base + "/api/kindle", {"id": "abc"})[0] == 404
    assert uploads == []


def test_kindle_sends_to_configured_address(server, monkeypatch):
    base, uploads = server
    monkeypatch.setattr(web.Handler, "kindle", {"to": "me@kindle.com", "sender": "s", "host": "h", "port": 25})
    assert request(base + "/api/state")[1]["kindle"] is True
    assert request(base + "/api/kindle", {"id": "abc", "to": "x@evil"}) == (200, {})
    assert request(base + "/api/kindle", {"id": "../abc"})[0] == 404
    assert uploads == [("kindle", "abc.html", "me@kindle.com")]


def test_post_requires_json(server):
    base, _ = server
    assert request(base + "/api/jobs", {"url": "x"}, "text/plain")[0] == 415


def test_jobs_reject_non_youtube_urls(server):
    base, _ = server
    assert request(base + "/api/jobs", {"url": "https://example.com/watch?v=x"}) == (400, {"error": "not a YouTube URL"})


def test_publish_module_updates_existing_page(tmp_path, monkeypatch):
    path = tmp_path / "abc.html"
    path.write_text("<html></html>")
    (tmp_path / "abc.json").write_text(json.dumps({"published": {"site_id": "s", "url": "u", "update_key": "k"}}))
    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

        def read(self):
            return b"{}"

    def fake_urlopen(req, timeout):
        seen.append((req.method, req.full_url, req.get_header("Authorization")))
        return Response()

    monkeypatch.setattr(publish_module.urllib.request, "urlopen", fake_urlopen)
    assert publish_module.publish(path) == "u"
    assert seen == [("PUT", publish_module.API + "/s", "Bearer k")]
