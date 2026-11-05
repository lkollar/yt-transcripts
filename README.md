# YouTube transcripts

Fetch a video's subtitles with yt-dlp. Manual subtitles are preferred; automatic captions are used when manual subtitles are unavailable. The saved text includes video metadata and the subtitle source.

## Setup

```sh
uv sync
```

## Usage

```sh
uv run fetch_transcript.py "https://youtu.be/JGtkTjn4120?is=bLbbuQKd-bAs_87Q" --stdout
uv run fetch_transcript.py "https://youtu.be/JGtkTjn4120?is=bLbbuQKd-bAs_87Q" --timestamps
```

Both commands save `transcripts/JGtkTjn4120.txt`; the second adds timestamps and overwrites the first. The video's original language is used by default: use `--lang` to override it, but note YouTube tends to answer machine-translated tracks with HTTP 429. Use `--out-dir PATH` to change the output directory. If YouTube requires sign-in, pass `--cookies-from-browser chrome` (or another browser supported by yt-dlp). Keep browser cookies private.

## HTML report

```sh
uv run yt_report.py URL --open
```

Fetches the transcript, pipes it to `claude -p`, saves a self-contained HTML report to `reports/<video_id>.html`. Options: `--model`, `--lang`, `--out-dir`, `--cookies-from-browser`. Needs the `claude` CLI on PATH.

## Web UI

```sh
uv run web.py
tailscale serve --bg --https 8446 http://127.0.0.1:8765
```

Submit a URL and browse past reports at `https://<machine>.<tailnet>.ts.net:8446`. Options: `--host`, `--port`, `--model`, `--out-dir`, `--cookies-from-browser`.

For a permanent service, `flake.nix` exports a NixOS module (`services.yt-transcripts`) which runs the web UI as a user service and adds the Tailscale route.

There is no authentication, so keep the default `127.0.0.1` host and let `tailscale serve` limit access to your tailnet. Anyone on the tailnet can start reports, which run on your Claude account. Reports are generated one at a time; failed jobs stay listed until the server restarts.
