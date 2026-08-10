import http.server
import argparse
import json
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

parser = argparse.ArgumentParser(description="Serve a browser engine/game deployment")
parser.add_argument("--root", type=Path, default=PROJECT_ROOT / "out" / "game")
parser.add_argument("--port", type=int, default=1111)
parser.add_argument("--serverless", action=argparse.BooleanOptionalAction, default=None)
args = parser.parse_args()

CLIENT_ROOT = args.root.resolve()
BUILD_MODE_FILE = PROJECT_ROOT / "build_mode.json"
PORT = args.port


serverless_enabled = bool(args.serverless) if args.serverless is not None else False
if args.serverless is None and BUILD_MODE_FILE.exists():
    with BUILD_MODE_FILE.open("r", encoding="utf-8") as f:
        serverless_enabled = bool(json.load(f).get("serverless", False))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(CLIENT_ROOT), **kwargs)

    def do_GET(self):
        req_path = self.path.split('?')[0].split('#')[0]
        if req_path == "/config.js":
            body = (
                "window.QUIC_URL = null;\n"
                f"window.SERVERLESS = {str(serverless_enabled).lower()};\n"
            )
            encoded = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        super().do_GET()

    def log_message(self, format, *args):
        print(f"[HTTP] {self.address_string()} - {format % args}", flush=True)

    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


Handler.extensions_map.update({
    ".wasm": "application/wasm",
    ".js": "application/javascript",
})


if not (CLIENT_ROOT / "index.html").is_file():
    raise SystemExit(f"Deployment does not contain index.html: {CLIENT_ROOT}")

print(f"Starting HTTP server on http://localhost:{PORT} from {CLIENT_ROOT}", flush=True)
httpd = http.server.ThreadingHTTPServer(("", PORT), Handler)
print("READY: Serving index.html and other files.", flush=True)
httpd.serve_forever()
