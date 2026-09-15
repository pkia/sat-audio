# sat-audio — live NOAA satellite audio tap

Hear weather satellites as they pass over. A single-file stdlib Python server
that streams the current (or most recent) NOAA APT satellite capture as MP3,
about two minutes behind the live edge, to any browser on the LAN.

- **Live edge** — if a pass is being recorded right now, the stream starts
  ~2 min behind live and follows the recorder as data lands
- **Fallback** — no live pass? it plays back the most recent completed capture
- **Tiny** — Python stdlib + ffmpeg, no framework, no build step
- Pairs with a NOAA APT recorder (e.g. an RTL-SDR + AtakCSJ-style flow, or
  wxapt); it just watches a directory of `.wav` capture files

## Configuration (environment)

| Variable | Default | What |
|---|---|---|
| `SAT_AUDIO_DIR` | `/home/ev/maritime-dashboard/noaa_audio` (legacy default) | directory of capture `.wav` files |

The legacy default points at a maritime-dashboard capture dir; set the env
vars for any other layout.

## Endpoints

| Path | What |
|---|---|
| `/` | player page |
| `/stream.mp3` | live/fallback MP3 stream |
| `/status.json` | current file, live flag, listener count |

## Run

    SAT_AUDIO_DIR=/path/to/captures python3 server.py   # :8085

Pull-based deploy with health check and auto-rollback is included
(`deploy/`), driven by a systemd timer.
