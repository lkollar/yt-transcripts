import json

import pytest

from yt_transcripts import Error
from yt_transcripts.report import add_stylesheet, extract_html, read_meta, write_meta


def test_extract_html_strips_commentary():
    out = "Here you go:\n<!DOCTYPE html><html><body>x</body></html>\nDone."
    assert extract_html(out) == "<!DOCTYPE html><html><body>x</body></html>\n"


def test_extract_html_requires_document():
    with pytest.raises(Error):
        extract_html("no html here")


def test_add_stylesheet_replaces_model_styles():
    html = add_stylesheet("<html><head><style>body{color:red}</style></head><body></body></html>")
    assert "color:red" not in html
    assert html.count("<style>") == 1
    assert "fonts.googleapis.com" in html


def test_add_stylesheet_requires_head():
    with pytest.raises(Error):
        add_stylesheet("<html><body></body></html>")


def test_meta_roundtrip(tmp_path):
    path = tmp_path / "abc.html"
    assert read_meta(path) is None
    write_meta(path, {"id": "abc"})
    assert json.loads((tmp_path / "abc.json").read_text()) == {"id": "abc"}
    assert read_meta(path) == {"id": "abc"}
