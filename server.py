#!/usr/bin/env python3
"""Live satellite audio tap (stdlib only).
Streams the current/most recent SDR capture as MP3 via ffmpeg.
Player page + stream on :8085."""
import glob
import json
import os
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AUDIO_DIR = "/home/ev/maritime-dashboard/noaa_audio"
STATE = "/home/ev/maritime-dashboard/noaa_state.json"
PORT = 8085
LIVE_SKIP_BYTES = 20 * 1024 * 1024  # ~2 min behind live at 176 kB/s


def newest_wav():
    wavs = [w for w in glob.glob(os.path.join(AUDIO_DIR, "*.wav"))
            if os.path.getsize(w) > 1_000_000]  # skip empty/failed captures
    return max(wavs, key=os.path.getmtime) if wavs else None


def capture_live():
    try:
        return json.load(open(STATE)).get("capture_in_progress") is True
    except Exception:
        return False


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_page()
        elif self.path == "/stream.mp3":
            self.send_stream()
        elif self.path == "/status.json":
            wav = newest_wav()
            body = json.dumps({
                "live": capture_live(),
                "file": os.path.basename(wav) if wav else None,
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def send_page(self):
        wav = newest_wav()
        name = os.path.basename(wav) if wav else "none yet"
        live = capture_live()
        dot = "#ff5252;animation:p 1s infinite" if live else "#5a6b8c"
        status = "🛰️ LIVE capture in progress" if live else "⏸️ no capture right now"
        note = ("You are hearing the pass about 2 minutes behind live."
                if live else "Playing back the most recent recorded pass.")
        html = f"""<!doctype html><html><head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>Satellite audio</title><style>
 body{{font-family:-apple-system,system-ui,sans-serif;background:#0b1020;color:#e8ecf5;
      max-width:640px;margin:40px auto;padding:0 16px}}
 h1{{font-size:1.3rem}} audio{{width:100%;margin:16px 0}}
 .dot{{display:inline-block;width:10px;height:10px;border-radius:50%;
      background:{dot};margin-right:8px}}
 @keyframes p{{50%{{opacity:.3}}}}
 .muted{{color:#8fa0bf;font-size:.9rem}}
</style></head><body>
<h1><span class="dot"></span>Satellite downlink</h1>
<p>{status}</p>
<p class="muted">Source: {name}<br>{note}</p>
<audio controls autoplay preload="none" src="/stream.mp3"></audio>
<p class="muted">Audio ends when the pass ends — reopen this page
during any capture to listen live.</p>
</body></html>""".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def send_stream(self):
        wav = newest_wav()
        if not wav:
            self.send_error(503, "no recordings yet")
            return
        live = capture_live()
        skip = LIVE_SKIP_BYTES if live else 0

        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()

        stop = threading.Event()

        def pump(src, dst, is_audio):
            try:
                while not stop.is_set():
                    if is_audio:
                        chunk = src.read1(65536)  # return as soon as data available
                        if not chunk:
                            break
                        dst.write(chunk)
                    else:
                        chunk = src.read(65536)
                        if chunk:
                            dst.write(chunk)
                            dst.flush()  # don't buffer in Python
                        else:
                            time.sleep(0.4)  # live edge: wait for recorder
                            dst.flush()
            except (BrokenPipeError, ConnectionResetError, ValueError, OSError):
                pass
            finally:
                stop.set()
                if not is_audio:
                    try:
                        src.close()  # stdin of ffmpeg
                    except Exception:
                        pass

        try:
            f = open(wav, "rb")
            if skip:
                f.seek(0, os.SEEK_END)
                f.seek(max(0, f.tell() - skip))
            proc = subprocess.Popen(
                ["ffmpeg", "-hide_banner", "-loglevel", "error",
                 "-f", "s16le", "-ar", "44100", "-ac", "1", "-i", "pipe:0",
                 "-vn", "-acodec", "libmp3lame", "-ab", "96k",
                 "-f", "mp3", "pipe:1"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=open("/tmp/sat-ffmpeg.log", "ab"))
            threading.Thread(
                target=pump, args=(f, proc.stdin, False), daemon=True).start()
            pump(proc.stdout, self.wfile, True)
        except Exception:
            pass
        finally:
            stop.set()
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                self.wfile.flush()
            except Exception:
                pass


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *a: os._exit(0))
    signal.signal(signal.SIGINT, lambda *a: os._exit(0))
    os.chdir("/tmp")  # don't hold cwd
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
