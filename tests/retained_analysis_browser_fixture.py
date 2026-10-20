"""Isolated renderer fixture, not an application/authorization server."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
HTML = b'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Retained analysis renderer fixture</title><link rel="stylesheet" href="/tests/fixtures/retained-analysis-browser.css"><main><div id="analysis"></div></main><script src="/static/vendor/retained-analysis/vega.min.js"></script><script src="/static/vendor/retained-analysis/vega-lite.min.js"></script><script src="/static/vendor/retained-analysis/vega-embed.min.js"></script><script src="/static/vendor/retained-analysis/vega-interpreter.min.js"></script><script src="/static/retained-analysis.js"></script><script src="/tests/fixtures/retained-analysis-browser.js"></script></html>'''


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        super().end_headers()

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML)
        elif self.path.startswith('/static/vendor/retained-analysis/') or self.path in (
                '/static/retained-analysis.js', '/static/retained-checkpoint-curve.vl.json',
                '/tests/fixtures/retained-analysis-browser.js', '/tests/fixtures/retained-analysis-browser.css'):
            super().do_GET()
        else:
            self.send_error(404)


if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    print(server.server_port, flush=True)
    server.serve_forever()
