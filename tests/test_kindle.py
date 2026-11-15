import io
import json
import xml.etree.ElementTree as ET
import zipfile

import pytest

from yt_transcripts import Error, kindle

REPORT = """<!DOCTYPE html><html><head><title>T</title><link rel="stylesheet" href="x"><style>p{}</style></head>
<body><div class="wrap"><header><h1>Title &amp; more</h1><img class="thumb" src="https://i.ytimg.com/x.jpg"><br></header>
<section class="idea" id="one"><div class="idea-head"><span class="label">Idea 1 · <a class="ts" href="https://y/?a=1&t=5" target="_blank">0:05</a></span><h2>First <em>idea</em></h2></div>
<div class="body"><p>Unclosed <b>bold<p>next</div></section>
<section class="idea"><h2>Second</h2><label><input type="checkbox"><span>Do it</span></label></section>
<details open><summary>References</summary><ul><li>x</li></ul></details>
<script>alert(1)</script></div></body></html>
"""


@pytest.fixture
def report(tmp_path):
    path = tmp_path / "abc.html"
    path.write_text(REPORT)
    (tmp_path / "abc.json").write_text(json.dumps({
        "id": "abc", "title": "A <video>", "channel": "Chan", "url": "https://youtu.be/abc",
        "subtitle_source": "subtitles:de-orig", "created": 1,
    }))
    (tmp_path / "abc.jpg").write_bytes(b"\xff\xd8\xff\xe0jpeg")
    return path


def test_epub_structure(report):
    z = zipfile.ZipFile(io.BytesIO(kindle.epub(report)))
    first = z.infolist()[0]
    assert (first.filename, first.compress_type) == ("mimetype", zipfile.ZIP_STORED)
    for name in z.namelist():
        if name.endswith((".xml", ".opf", ".xhtml")):
            ET.fromstring(z.read(name))
    body = z.read("OEBPS/report.xhtml").decode()
    assert "alert" not in body and "<img" not in body and "<input" not in body and "target=" not in body
    assert "☐ " in body and 'href="https://y/?a=1&amp;t=5"' in body
    nav = z.read("OEBPS/nav.xhtml").decode()
    assert '<a href="report.xhtml#one">First idea</a>' in nav
    assert '<a href="report.xhtml#part-1">Second</a>' in nav
    assert '<a href="report.xhtml#part-2">References</a>' in nav
    opf = z.read("OEBPS/content.opf").decode()
    assert "<dc:title>A &lt;video&gt;</dc:title>" in opf and "<dc:language>de</dc:language>" in opf
    assert z.read("OEBPS/cover.jpg").startswith(b"\xff\xd8")


def test_epub_without_cover(report, monkeypatch):
    report.with_suffix(".jpg").unlink()
    monkeypatch.setattr(kindle, "save_thumbnail", lambda path, video_id: None)
    z = zipfile.ZipFile(io.BytesIO(kindle.epub(report)))
    assert "OEBPS/cover.jpg" not in z.namelist()
    assert "cover" not in z.read("OEBPS/content.opf").decode()


def test_send_records_delivery(report, monkeypatch):
    sent = []

    class SMTP:
        def __init__(self, host, port, timeout):
            sent.append((host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

        def send_message(self, msg):
            sent.append((msg["To"], msg["From"], msg.get_payload()[1].get_filename()))

    monkeypatch.setattr(kindle.smtplib, "SMTP", SMTP)
    kindle.send(report, "me@kindle.com", "from@example.com", "relay", 2525)
    assert sent == [("relay", 2525), ("me@kindle.com", "from@example.com", "abc.epub")]
    assert "sent" in json.loads(report.with_suffix(".json").read_text())["kindle"]


def test_send_reports_relay_errors(report, monkeypatch):
    def refuse(*args, **kwargs):
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(kindle.smtplib, "SMTP", refuse)
    with pytest.raises(Error):
        kindle.send(report, "me@kindle.com", "from@example.com")
    assert "kindle" not in json.loads(report.with_suffix(".json").read_text())
