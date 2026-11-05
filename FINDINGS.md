# Findings: fetch_transcript.py 429

## Resolved
Not a PO token issue; "Likely cause" below is wrong. `pick_track` chose
`en`, a machine translation (`tlang=en`) of the auto-dubbed `ar` track.
Only that track 429s; all `-orig` tracks download fine. Fix: prefer
`<lang>-orig`, detect language from the audio format marked `original`
(`info["language"]` said `ar` for this English video).

## Symptom
`HTTP Error 429: Too Many Requests` when downloading subtitle URL
(`ydl.urlopen(track["url"])`). Same via `yt-dlp --write-subs` CLI.
Video: JGtkTjn4120. yt-dlp 2026.10.26 (latest).

## Tried (no fix)
- Upgrade yt-dlp: already latest
- `yt-dlp[default,curl-cffi]` impersonation: installed, still 429
- JS runtime (`--js-runtimes node`): still 429
- player_client web/mweb/tv/web_safari/android: 429, or formats
  unavailable, or (mweb) subs discarded: "require a PO Token"

## Likely cause
YouTube subtitles need a PO token ("Subs" context). yt-dlp warns:
"Some mweb client subtitles require a PO Token ... discarded".
Not fully proven: issue 13831 reports 429 mainly for auto-translated
tracks; IP rate limiting also possible. Enforcement seems A/B tested.

## Fix options
1. bgutil-ytdlp-pot-provider plugin (documented fix). Needs provider
   server built (clone repo, `npm ci`, `tsc`) + `pip install
   bgutil-ytdlp-pot-provider`. Build was blocked by auto-mode
   classifier (external code); needs user approval.
2. `--cookies-from-browser chrome` (logged-in session). Untested.
3. Read transcript from YouTube page via Chrome (one-off, no script fix).

## Changes made (uncommitted)
- `requirements.txt`: `yt-dlp[default,curl-cffi]`
- `fetch_transcript.py`: enable node/deno JS runtime; clear error on
  HTTPError (429 hint)

## Not done
- Transcript for README video not obtained
- README not updated (mention node/deno, PO token, curl-cffi)

## Sources
- https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide
- https://github.com/yt-dlp/yt-dlp/issues/13831
- https://github.com/yt-dlp/yt-dlp/issues/17395
