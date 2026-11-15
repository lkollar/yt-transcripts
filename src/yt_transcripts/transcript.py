"""Fetch the subtitles of a YouTube video as plain text using yt-dlp.

Usage:
    yt-transcript URL [--lang LANG] [--out-dir transcripts] [--timestamps]

Writes <out-dir>/<video_id>.txt (and prints it to stdout with --stdout).
Uses the video's original language unless --lang is given.
Prefers manual subtitles, falls back to auto-generated captions.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.networking.exceptions import HTTPError

from . import Error


def original_language(info):
    """Return the spoken language. info["language"] can be a dub on auto-dubbed videos."""
    for f in info.get("formats") or []:
        if "original" in (f.get("format_note") or "") and f.get("language"):
            return f["language"].split("-")[0]
    return (info.get("language") or "en").split("-")[0]


def pick_track(info, lang):
    """Return (track_list, source) choosing manual subs before automatic captions."""
    for source in ("subtitles", "automatic_captions"):
        tracks = info.get(source) or {}
        # <lang>-orig is the real ASR track; plain <lang> can be a machine
        # translation (tlang=), which YouTube answers with HTTP 429.
        preferred = [f"{lang}-orig", lang]
        for key in preferred + [k for k in tracks if k.split("-")[0] == lang and k not in preferred]:
            if key in tracks:
                return tracks[key], f"{source}:{key}"
    return None, None


def parse_json3(data, timestamps):
    """Remove rolling-caption overlap, preserving the start of new speech."""
    captions = []
    previous = []
    for event in data.get("events", []):
        words = re.sub(r"\s+", " ", "".join(
            seg.get("utf8", "") for seg in event.get("segs", [])
        )).strip().split()
        if not words:
            continue
        overlap = 0
        for size in range(min(len(previous), len(words)), 0, -1):
            if previous[-size:] == words[:size]:
                overlap = size
                break
        new_words = words[overlap:]
        previous = words
        if new_words:
            captions.append((event.get("tStartMs", 0) // 1000, " ".join(new_words)))

    if timestamps:
        return "\n".join(
            f"[{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}] {text}"
            for s, text in captions
        )

    paragraphs = []
    paragraph = []
    for _, text in captions:
        paragraph.append(text)
        if len(" ".join(paragraph)) >= 800 or (len(" ".join(paragraph)) >= 500 and re.search(r"[.!?][\"']?$", text)):
            paragraphs.append(" ".join(paragraph))
            paragraph = []
    if paragraph:
        paragraphs.append(" ".join(paragraph))
    return "\n\n".join(paragraphs)


def fetch(url, lang=None, timestamps=False, cookies_from_browser=None):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        # YouTube needs a JS runtime to solve player challenges
        "js_runtimes": {"node": {}, "deno": {}},
    }
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        lang = lang or original_language(info)
        tracks, source = pick_track(info, lang)
        if not tracks:
            raise Error(f"No '{lang}' subtitles found for {info['id']}")
        track = next((t for t in tracks if t.get("ext") == "json3"), None)
        if not track:
            raise Error(f"No json3 subtitle format available ({source})")
        try:
            raw = ydl.urlopen(track["url"]).read()
        except HTTPError as e:
            raise Error(
                f"Subtitle download failed ({source}): {e}\n"
                "HTTP 429 is expected for machine-translated tracks: drop --lang to use the "
                "original language. Otherwise retry with --cookies-from-browser BROWSER."
            )
    text = parse_json3(json.loads(raw), timestamps)
    meta = {
        "id": info["id"],
        "title": info.get("title"),
        "channel": info.get("channel"),
        "duration": info.get("duration"),
        "url": info.get("webpage_url"),
        "subtitle_source": source,
    }
    return meta, text


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("url")
    p.add_argument("--lang", help="subtitle language (default: the video's original language)")
    p.add_argument("--out-dir", default="transcripts")
    p.add_argument("--timestamps", action="store_true", help="prefix each caption line with [HH:MM:SS]")
    p.add_argument("--cookies-from-browser", metavar="BROWSER", help="load cookies from a browser supported by yt-dlp")
    p.add_argument("--stdout", action="store_true", help="print the transcript instead of only saving it")
    a = p.parse_args()

    try:
        meta, text = fetch(a.url, a.lang, a.timestamps, a.cookies_from_browser)
    except Error as e:
        raise SystemExit(f"error: {e}")
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    header = "\n".join(f"{k}: {v}" for k, v in meta.items())
    path = out / f"{meta['id']}.txt"
    path.write_text(f"{header}\n\n{text}\n", encoding="utf-8")
    print(f"Saved {path} ({len(text)} chars, {meta['subtitle_source']})", file=sys.stderr)
    if a.stdout:
        print(text)


if __name__ == "__main__":
    main()
