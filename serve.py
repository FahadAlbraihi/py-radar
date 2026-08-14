"""خادم محلي لتطبيق "رادار بايثون".

يقوم بأمرين:
  1) يقدّم ملفات التطبيق (index.html وغيرها).
  2) يعمل كبروكسي CORS على المسار /proxy?url=... حتى يستطيع المتصفح
     قراءة تغذيات RSS من مواقع لا ترسل ترويسات CORS.

التشغيل:
    python serve.py           # المنفذ الافتراضي 8000
    python serve.py 9000

ثم افتح الرابط المطبوع على شاشة الآيفون (نفس شبكة الواي فاي).
لا يحتاج أي مكتبات خارجية.
"""

from __future__ import annotations

import gzip
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TIMEOUT = 20

# طرفية ويندوز الافتراضية لا تدعم العربية — نجبرها على UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

MAX_BYTES = 5 * 1024 * 1024

# نطاقات مسموح بجلبها عبر البروكسي (حماية من استخدام الخادم كبروكسي مفتوح)
ALLOWED_HOSTS = (
    "news.google.com", "bing.com", "www.bing.com",
    "reddit.com", "www.reddit.com", "old.reddit.com",
    "realpython.com", "planetpython.org", "blog.python.org", "pypi.org",
    "youtube.com", "www.youtube.com",
    "hn.algolia.com", "dev.to", "api.stackexchange.com", "api.github.com",
    "academy.hsoub.com", "io.hsoub.com", "hsoub.com",
    "feeds.feedburner.com", "medium.com",
)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def host_allowed(netloc: str) -> bool:
    host = netloc.split(":")[0].lower()
    return any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802
        path, _, query = self.path.partition("?")
        if path.rstrip("/").endswith("/proxy") or path == "/proxy":
            return self.handle_proxy(urllib.parse.parse_qs(query))
        return super().do_GET()

    # -------- البروكسي --------
    def handle_proxy(self, params: dict[str, list[str]]):
        if "ping" in params:
            return self.send_bytes(b"pong", "text/plain; charset=utf-8")

        target = (params.get("url") or [""])[0]
        if not target:
            return self.send_bytes(b"missing url", "text/plain; charset=utf-8", 400)

        parsed = urllib.parse.urlparse(target)
        if parsed.scheme not in ("http", "https") or not host_allowed(parsed.netloc):
            return self.send_bytes(b"host not allowed", "text/plain; charset=utf-8", 403)

        req = urllib.request.Request(
            target,
            headers={
                "User-Agent": UA,
                "Accept": "application/rss+xml, application/xml, application/json, text/html;q=0.8, */*;q=0.5",
                "Accept-Language": "ar,en;q=0.8",
                "Accept-Encoding": "gzip",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                body = r.read(MAX_BYTES)
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                ctype = r.headers.get("Content-Type", "application/xml; charset=utf-8")
        except urllib.error.HTTPError as e:
            return self.send_bytes(f"upstream {e.code}".encode(), "text/plain; charset=utf-8", 502)
        except Exception as e:  # noqa: BLE001
            return self.send_bytes(str(e).encode(), "text/plain; charset=utf-8", 502)

        self.send_bytes(body, ctype)

    def send_bytes(self, body: bytes, ctype: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        # يمنع تخزين الصفحة قديمة أثناء التطوير
        if not self.path.startswith("/proxy"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        if "/proxy" in self.path:
            return
        super().log_message(fmt, *args)


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:  # noqa: BLE001
        return "127.0.0.1"
    finally:
        s.close()


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    handler = partial(Handler, directory=str(ROOT))
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)

    print("\n  رادار بايثون يعمل الآن")
    print(f"  على هذا الجهاز :  http://localhost:{port}/")
    print(f"  على الآيفون    :  http://{lan_ip()}:{port}/    (نفس شبكة الواي فاي)")
    print("\n  للإيقاف: Ctrl+C\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  تم الإيقاف.")
        server.shutdown()


if __name__ == "__main__":
    main()
