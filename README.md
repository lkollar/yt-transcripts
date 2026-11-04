# YouTube transcripts

Fetch a video's subtitles with yt-dlp. Manual subtitles are preferred; automatic captions are used when manual subtitles are unavailable. The saved text includes video metadata and the subtitle source.

## Setup

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```sh
python fetch_transcript.py "https://youtu.be/JGtkTjn4120?is=bLbbuQKd-bAs_87Q" --stdout
python fetch_transcript.py "https://youtu.be/JGtkTjn4120?is=bLbbuQKd-bAs_87Q" --timestamps
```

Both commands save `transcripts/JGtkTjn4120.txt`; the second adds timestamps and overwrites the first. Use `--lang en` to choose a language or `--out-dir PATH` to change the output directory. If YouTube requires sign-in, pass `--cookies-from-browser chrome` (or another browser supported by yt-dlp). Keep browser cookies private.

Workflow: fetch the transcript, summarise the saved text, then publish the summary as an artifact. Summarising and publishing are separate manual steps.
