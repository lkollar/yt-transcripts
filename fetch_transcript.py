#!/usr/bin/env python3
"""Fetch the subtitles of a YouTube video as plain text using yt-dlp.

Usage:
    python fetch_transcript.py URL [--lang en] [--out-dir transcripts] [--timestamps]

Writes <out-dir>/<video_id>.txt (and prints it to stdout with --stdout).
Prefers manual subtitles, falls back to auto-generated captions.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from yt_dlp import YoutubeDL


def pick_track(info, lang):
    """Return (track_list, source) choosing manual subs before automatic captions."""
    for source in ("subtitles", "automatic_captions"):
        tracks = info.get(source) or {}
        # exact match first, then any variant like en-US / en-orig
        for key in [lang] + [k for k in tracks if k.split("-")[0] == lang and k != lang]:
            if key in tracks:
                return tracks[key], f"{source}:{key}"
    return None, None


def parse_json3(data, timestamps):
    lines = []
    for ev in data.get("events", []):
        segs = ev.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs).replace("\n", " ").strip()
        if not text:
            continue
        if timestamps:
            s = int(ev.get("tStartMs", 0) / 1000)
            text = f"[{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}] {text}"
        lines.append(text)
    return lines


def fetch(url, lang="en", timestamps=False):
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        tracks, source = pick_track(info, lang)
        if not tracks:
            raise SystemExit(f"No '{lang}' subtitles found for {info['id']}")
        track = next((t for t in tracks if t.get("ext") == "json3"), None)
        if not track:
            raise SystemExit(f"No json3 subtitle format available ({source})")
        raw = ydl.urlopen(track["url"]).read()
    lines = parse_json3(json.loads(raw), timestamps)
    if not timestamps:
        # join into paragraphs of reasonable size
        text = re.sub(r"\s+", " ", " ".join(lines))
    else:
        text = "\n".join(lines)
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
    p.add_argument("--lang", default="en")
    p.add_argument("--out-dir", default="transcripts")
    p.add_argument("--timestamps", action="store_true", help="prefix each caption line with [HH:MM:SS]")
    p.add_argument("--stdout", action="store_true", help="print the transcript instead of only saving it")
    a = p.parse_args()

    meta, text = fetch(a.url, a.lang, a.timestamps)
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
