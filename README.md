# yt-transcripts

Turn YouTube videos into readable HTML reports. Subtitles are fetched with
[yt-dlp](https://github.com/yt-dlp/yt-dlp) and summarised by the
[Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI into a report
organised by idea, with action steps and linked references where the video
supports them.

## Requirements

- Python 3.13+ and [uv](https://docs.astral.sh/uv/)
- Node.js or Deno: yt-dlp needs a JS runtime to solve YouTube player challenges
- `claude` on `PATH` and logged in (reports only)

## Install

```sh
uv tool install git+https://github.com/lkollar/yt-transcripts
```

Or run from a checkout with `uv run <command>`.

## Transcripts

```sh
yt-transcript "https://youtu.be/JGtkTjn4120" --stdout
yt-transcript "https://youtu.be/JGtkTjn4120" --timestamps
```

Both save `transcripts/JGtkTjn4120.txt` with the video's metadata; the second
adds timestamps. Manual subtitles are preferred over automatic captions. The
video's original language is used by default: `--lang` overrides it, but YouTube
tends to answer machine-translated tracks with HTTP 429. Use `--out-dir PATH` to
change the output directory. If YouTube requires sign-in, pass
`--cookies-from-browser chrome` (or another browser supported by yt-dlp).

## Reports

```sh
yt-report URL --open
```

Saves a self-contained report to `reports/<video_id>.html`, with metadata in
`reports/<video_id>.json` and the thumbnail in `reports/<video_id>.jpg`. `claude` gets `WebSearch` and `WebFetch` to find
reference links, so reports with many references take longer. It runs without
your Claude settings, MCP servers or project context, since the transcript is
untrusted input. Options: `--model`, `--lang`, `--out-dir`,
`--cookies-from-browser`.

## Web UI

```sh
yt-report-web
```

Submit URLs and browse past reports at `http://127.0.0.1:8765`. Reports are
generated one at a time; failed jobs stay listed until the server restarts.
Options: `--host`, `--port`, `--model`, `--out-dir`, `--cookies-from-browser`.

There is no authentication. Anyone who can reach the UI can start reports, which
run on your Claude account, and publish reports publicly. Keep the default
`127.0.0.1` host and put it behind a private network or an authenticating
reverse proxy, for example
`tailscale serve --bg --https 8443 http://127.0.0.1:8765`.

### Sharing

The Publish button uploads a report to [ht-ml.app](https://ht-ml.app/) as a
public page: anyone with the link can read it, and it can't be deleted. Update
re-uploads it to the same URL. The page's update key is kept in the report's
`.json` file. See ht-ml.app's [terms](https://ht-ml.app/terms) before
publishing.

### Send to Kindle

With `--kindle-to` and `--kindle-from`, each report gets a Send to Kindle
button, which emails it as an EPUB to your
[Send to Kindle address](https://www.amazon.com/sendtokindle/email). Add the
sender to the account's approved e-mail list first. Mail goes through an SMTP
relay that accepts it without authentication, `localhost:25` by default, such
as a local MTA forwarding to your mail provider (`--smtp-host`, `--smtp-port`).
The video's thumbnail, saved next to each report, becomes the book's cover.

## NixOS

`flake.nix` exports a package and a NixOS module which runs the web UI as a user
service, using that user's Claude login:

```nix
services.yt-transcripts = {
  enable = true;
  user = "alice";
};
```

Reports are kept in `~/.local/state/yt-transcripts/reports`. The UI listens on
`127.0.0.1:8765` (`port` option); exposing it is up to you. Set `kindle.to` and
`kindle.from` to enable Send to Kindle (`kindle.smtpHost`, `kindle.smtpPort`).

## Development

```sh
uv sync
uv run pytest
```

## License

MIT
