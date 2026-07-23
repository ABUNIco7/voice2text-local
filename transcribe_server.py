"""
Audio-to-Text Local Server
Works with voice2text.html

Usage: python transcribe_server.py
Port: http://localhost:8765
"""
import os
import sys
import tempfile
import traceback
import threading
import json
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# ── Globals ──
current_model = None
current_model_name = None


def load_model():
    global current_model, current_model_name
    if current_model is not None:
        return current_model
    try:
        import torch
        has_cuda = torch.cuda.is_available()
        ct = "float16" if has_cuda else "int8"
        device = "cuda" if has_cuda else "cpu"
        sys.stderr.write(f"[Model] Device={device}, compute_type={ct}\n")
    except ImportError:
        device = "cpu"
        ct = "int8"
        sys.stderr.write("[Model] torch not found, using CPU int8\n")
    from faster_whisper import WhisperModel
    model_name = "base"
    sys.stderr.write(f"[Model] Loading faster-whisper '{model_name}' on {device}...\n")
    current_model = WhisperModel(model_name, device=device, compute_type=ct)
    current_model_name = model_name
    sys.stderr.write("[Model] Loaded!\n")
    return current_model


def to_srt(segments):
    lines = []
    for i, seg in enumerate(segments, 1):
        s, e = seg["start"], seg["end"]
        sh, sm, ss = int(s//3600), int((s%3600)//60), int(s%60)
        eh, em, es = int(e//3600), int((e%3600)//60), int(e%60)
        sms, ems = int((s-int(s))*1000), int((e-int(e))*1000)
        lines.append(f"{i}\n{sh:02d}:{sm:02d}:{ss:02d},{sms:03d} --> {eh:02d}:{em:02d}:{es:02d},{ems:03d}\n{seg['text'].strip()}\n")
    return "\n".join(lines)


def transcribe(audio_path):
    model = load_model()
    sys.stderr.write(f"[Transcribe] {audio_path}\n")
    segments, info = model.transcribe(audio_path, language="zh", beam_size=5)
    seg_list = [{"start": float(s.start), "end": float(s.end), "text": s.text} for s in segments]
    text = " ".join(seg["text"] for seg in seg_list)
    duration = float(info.duration) if info.duration else 0.0
    sys.stderr.write(f"[Done] {len(seg_list)} segs, {len(text)} chars\n")
    return {"text": text, "segments": seg_list, "duration": duration, "srt": to_srt(seg_list)}


# ── Robust multipart parser ──
def parse_multipart(body_bytes, content_type):
    # Extract boundary from Content-Type
    m = re.search(r'\bboundary=(.+?)(?:;|$)', content_type, re.IGNORECASE)
    if not m:
        sys.stderr.write(f"[Multipart] No boundary found in: {content_type[:60]}\n")
        return {}
    # Strip quotes and surrounding dashes that some clients include
    raw = m.group(1).strip().strip('"').strip("'")
    # RFC 2046: boundary may start with "--" in the header; strip exactly 2 leading dashes
    if raw.startswith('--'):
        raw = raw[2:]
    sep = ("--" + raw).encode()
    sys.stderr.write(f"[Multipart] boundary='{raw}', sep={sep}\n")

    parts = body_bytes.split(sep)
    sys.stderr.write(f"[Multipart] split into {len(parts)} parts\n")
    result = {}
    for part in parts:
        # Strip leading/trailing whitespace and dashes
        part = part.strip(b'\r\n-')
        if not part:
            continue
        idx = part.find(b'\r\n\r\n')
        if idx == -1:
            continue
        hdr_bytes = part[:idx]
        file_data = part[idx+4:]
        # Parse headers using email parser (handles folding, encoding correctly)
        from email.parser import Parser
        from email.policy import default as email_policy
        hdrs = Parser(policy=email_policy).parsestr(hdr_bytes.decode('latin-1', errors='replace'))
        cd = hdrs.get('Content-Disposition', '')
        mn = re.search(r'name="([^"]+)"', cd)
        if not mn:
            continue
        name = mn.group(1)
        mf = re.search(r'filename="([^"]+)"', cd)
        result[name] = {
            'filename': mf.group(1) if mf else None,
            'data': file_data,
        }
        sys.stderr.write(f"[Multipart] field '{name}', file='{result[name]['filename']}', size={len(file_data)}\n")
    return result


# ── HTTP Handler ──
class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[HTTP] {self.address_string()} {fmt % args}\n")

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/", "/index.html"):
            base = os.path.dirname(os.path.abspath(__file__))
            fpath = os.path.join(base, "voice2text.html")
            if os.path.exists(fpath):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                with open(fpath, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, "voice2text.html not found")
        elif p == "/status":
            try:
                load_model()
                self.send_json({"ok": True, "model": current_model_name or "base", "lang": "zh"})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
        else:
            self.send_error(404)

    def do_POST(self):
        p = urlparse(self.path).path
        if p == "/transcribe":
            self.handle_transcribe()
        else:
            self.send_error(404)

    def handle_transcribe(self):
        try:
            cl = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(cl)
            content_type = self.headers.get("Content-Type", "")
            sys.stderr.write(f"[POST] CL={cl}, CT={content_type[:80]}\n")
            sys.stderr.flush()

            files = parse_multipart(body, content_type)

            if "file" not in files:
                sys.stderr.write(f"[POST] ERROR: keys={list(files.keys())}\n")
                self.send_json({"error": "No file uploaded"}, 400)
                return

            file_data = files["file"]
            filename = file_data["filename"] or "upload"
            sys.stderr.write(f"[Upload] {filename} ({len(file_data['data'])} bytes)\n")

            ext = os.path.splitext(filename)[1].lower() or ".mp3"
            fd, tmp_path = tempfile.mkstemp(suffix=ext)
            os.close(fd)
            with open(tmp_path, "wb") as f:
                f.write(file_data["data"])

            result = [None]
            error = [None]

            def run():
                try:
                    result[0] = transcribe(tmp_path)
                except Exception as e:
                    error[0] = traceback.format_exc()

            t = threading.Thread(target=run)
            t.start()
            t.join()

            try:
                os.unlink(tmp_path)
            except Exception:
                pass

            if error[0]:
                sys.stderr.write(f"[Error] {error[0]}\n")
                self.send_json({"error": error[0]}, 500)
                return

            self.send_json(result[0])

        except Exception as e:
            traceback.print_exc()
            self.send_json({"error": str(e)}, 500)


def main():
    # Railway / Heroku style: use PORT env var when available
    port = int(os.environ.get("PORT", "8765"))
    host = "0.0.0.0"
    print("=" * 45)
    print("  [V2T] Audio-to-Text Local Server")
    print("=" * 45)
    print(f"  Listening on http://{host}:{port}")
    print("  Ctrl+C to stop")
    print("=" * 45)
    server = HTTPServer((host, port), Handler)
    print(f"[Server] Ready on {host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Server] Stopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
