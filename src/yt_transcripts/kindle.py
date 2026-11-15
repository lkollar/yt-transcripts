"""Send reports to a Kindle as EPUB, by email through an SMTP relay."""
import io
import re
import smtplib
import time
import zipfile
from email.message import EmailMessage
from html import escape
from html.parser import HTMLParser
from pathlib import Path

from . import Error
from .report import read_meta, save_thumbnail, write_meta

STYLESHEET = Path(__file__).with_name("kindle.css")

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
# Dropped with their content: page furniture, and images, which are all remote
DROP = {
    "head", "script", "style", "img", "iframe", "object", "embed", "svg", "video", "audio", "form", "button",
    "select", "textarea", "link", "meta", "base",
}
# Dropped, keeping their content
UNWRAP = {"html", "body"}
# Kindle doesn't render <details>
RENAME = {"details": "div", "summary": "h2"}
ATTRS = {"href", "id", "class", "colspan", "rowspan", "start", "lang"}
INVALID_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")
SAFE_HREF = re.compile(r"(https?:|mailto:|#)", re.IGNORECASE)


def clean(text):
    """Make metadata safe for XML and email headers: no control characters or line breaks."""
    return " ".join(INVALID_XML.sub("", text).split())


class XHTMLWriter(HTMLParser):
    """Re-serialise a report's body as well-formed XHTML, collecting a table of contents.

    Each section gets an id, and its first heading becomes a contents entry.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.stack = []
        # The dropped element being skipped, and how deeply it's nested in itself
        self.skip = None
        self.depth = 0
        self.toc = []
        self.anchor = None
        self.heading = None
        self.ids = 0

    def handle_starttag(self, tag, attrs):
        if self.skip == "head" and tag == "body":
            self.skip = None
        if self.skip:
            self.depth += tag == self.skip
            return
        if tag in DROP:
            if tag not in VOID:
                self.skip, self.depth = tag, 1
            return
        if tag in UNWRAP or not re.fullmatch(r"[a-z][a-z0-9-]*", tag):
            return
        if tag == "input":
            if dict(attrs).get("type") == "checkbox":
                self.out.append("☐ ")
            return
        attrs = {k: v for k, v in attrs if k in ATTRS and v is not None and (k != "href" or SAFE_HREF.match(v))}
        if tag in ("section", "details"):
            if "id" not in attrs:
                self.ids += 1
                attrs["id"] = f"part-{self.ids}"
            self.anchor = attrs["id"]
        tag = RENAME.get(tag, tag)
        if tag == "h2" and self.anchor:
            self.heading = []
        rendered = "".join(f' {k}="{escape(INVALID_XML.sub("", v))}"' for k, v in attrs.items())
        if tag in VOID:
            self.out.append(f"<{tag}{rendered}/>")
        else:
            self.out.append(f"<{tag}{rendered}>")
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if self.skip:
            if tag == self.skip:
                self.depth -= 1
                if not self.depth:
                    self.skip = None
            return
        tag = RENAME.get(tag, tag)
        if tag not in self.stack:
            return
        if tag == "h2" and self.heading is not None:
            if text := " ".join("".join(self.heading).split()):
                self.toc.append((self.anchor, text))
            self.heading = self.anchor = None
        while (open_tag := self.stack.pop()) != tag:
            self.out.append(f"</{open_tag}>")
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if self.skip:
            return
        data = INVALID_XML.sub("", data)
        if self.heading is not None:
            self.heading.append(data)
        self.out.append(escape(data, quote=False))

    def result(self):
        return "".join(self.out) + "".join(f"</{t}>" for t in reversed(self.stack))


def xhtml_page(title, lang, body, head=""):
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{lang}" xml:lang="{lang}">\n'
        f"<head><meta charset=\"utf-8\"/><title>{escape(title)}</title>{head}</head>\n<body>{body}</body>\n</html>\n"
    )


def epub(path):
    """Build an EPUB of a report, with the video's thumbnail as its cover when available."""
    meta = read_meta(path) or {}
    title = clean(meta.get("title") or "") or path.stem
    channel, url = clean(meta.get("channel") or ""), clean(meta.get("url") or "")
    # subtitle_source is like "subtitles:en-orig"
    lang = re.sub(r"[^\w-]", "", meta.get("subtitle_source", "").rpartition(":")[2].split("-")[0]) or "en"
    writer = XHTMLWriter()
    writer.feed(path.read_text(encoding="utf-8"))
    writer.close()
    toc = writer.toc or [(None, title)]
    nav = "".join(
        f'<li><a href="report.xhtml{"#" + escape(anchor) if anchor else ""}">{escape(text)}</a></li>'
        for anchor, text in toc
    )
    cover = save_thumbnail(path, path.stem)
    if cover and not cover.read_bytes().startswith(b"\xff\xd8"):
        # Not a JPEG, so fetch it again next time
        cover.unlink()
        cover = None
    modified = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(meta.get("created", time.time())))
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid" xml:lang="{lang}">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="uid">urn:youtube:{escape(path.stem)}</dc:identifier>
<dc:title>{escape(title)}</dc:title>
<dc:language>{lang}</dc:language>
{f"<dc:creator>{escape(channel)}</dc:creator>" if channel else ""}
{f"<dc:source>{escape(url)}</dc:source>" if url else ""}
<meta property="dcterms:modified">{modified}</meta>
{'<meta name="cover" content="cover"/>' if cover else ""}
</metadata>
<manifest>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
{'<item id="cover-page" href="cover.xhtml" media-type="application/xhtml+xml"/>' if cover else ""}
<item id="report" href="report.xhtml" media-type="application/xhtml+xml"/>
<item id="css" href="style.css" media-type="text/css"/>
{'<item id="cover" href="cover.jpg" media-type="image/jpeg" properties="cover-image"/>' if cover else ""}
</manifest>
<spine>{'<itemref idref="cover-page"/>' if cover else ""}<itemref idref="report"/></spine>
</package>
"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        # The mimetype must come first, uncompressed
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>'
            "</container>\n"
        ))
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/nav.xhtml", xhtml_page(
            title, lang, f'<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>{nav}</ol></nav>',
        ))
        z.writestr("OEBPS/report.xhtml", xhtml_page(
            title, lang, writer.result(), '<link rel="stylesheet" type="text/css" href="style.css"/>',
        ))
        z.writestr("OEBPS/style.css", STYLESHEET.read_text(encoding="utf-8"))
        if cover:
            # Kindle's converter picks the cover up more reliably from a page of its own
            z.writestr("OEBPS/cover.xhtml", xhtml_page(
                title, lang, '<div style="text-align: center"><img src="cover.jpg" alt="" style="max-width: 100%"/></div>',
            ))
            z.write(cover, "OEBPS/cover.jpg")
    return buf.getvalue()


def send(path, to, sender, host="localhost", port=25):
    """Email a report as EPUB to a Kindle address and record when it was sent.

    The relay must accept mail without authentication, like a local MTA, and the
    sender must be on the Kindle account's approved list.
    """
    meta = read_meta(path) or {}
    title = clean(meta.get("title") or "") or path.stem
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = title
    msg.set_content("Sent by yt-report.")
    # Kindle titles personal documents after the attachment's name
    name = re.sub(r'[\\/:*?"<>|\s]+', " ", title).strip()[:100] or path.stem
    msg.add_attachment(epub(path), maintype="application", subtype="epub+zip", filename=f"{name}.epub")
    try:
        with smtplib.SMTP(host, port, timeout=60) as smtp:
            smtp.send_message(msg)
    except OSError as e:
        raise Error(f"sending to Kindle failed: {e}")
    meta["kindle"] = {"sent": int(time.time())}
    write_meta(path, meta)
