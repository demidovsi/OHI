"""Бывший сервис Cloud Run llm-web: постоянный редирект на ohi-web с тем же путём и параметрами — чтобы
работали ссылки, отправленные чат-ботом до переименования (21.10.2026)."""
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TARGET = os.environ.get('TARGET', 'https://ohi-web-16542874441.europe-central2.run.app').rstrip('/')


class Redirect(BaseHTTPRequestHandler):
    def _redirect(self):
        self.send_response(301)
        self.send_header('Location', TARGET + self.path)
        self.send_header('Content-Length', '0')
        self.end_headers()

    do_GET = do_HEAD = do_POST = _redirect


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', 8080))), Redirect).serve_forever()
