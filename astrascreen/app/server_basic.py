"""Built-in web server (Python standard library only). Used when FastAPI is not installed."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import urllib.parse
from . import api


class Handler(BaseHTTPRequestHandler):
    def _do(self, method):
        u = urllib.parse.urlsplit(self.path)
        query = dict(urllib.parse.parse_qsl(u.query))
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        status, ctype, data, extra = api.handle(method, u.path, query, dict(self.headers), body)
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in extra.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self): self._do("GET")
    def do_POST(self): self._do("POST")
    def log_message(self, fmt, *args): pass


def serve(host, port):
    api.startup()
    ThreadingHTTPServer((host, port), Handler).serve_forever()
