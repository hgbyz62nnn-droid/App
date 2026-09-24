"""Notification capture webhook (step A): python -m p2pbot.capture

Listens on 127.0.0.1 only; Caddy terminates HTTPS in front of it. Every authorised POST to
/hook/notify is appended as one JSON line to data/notifications.jsonl. Nothing is parsed, matched
or forwarded yet - this only collects real samples for building the payment parser.

Accepted input (so MacroDroid quoting can never break it): JSON body, form-encoded body,
or query parameters, with fields app, title, text, time, source, test. Anything else is kept raw.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from dotenv import dotenv_values

log = logging.getLogger("p2pbot.capture")

ROOT = Path(__file__).resolve().parent.parent
PATH = "/hook/notify"
TOKEN_HEADER = "X-Webhook-Token"
MAX_BODY = 16 * 1024
MAX_FILE = 50 * 1024 * 1024
FIELDS = ("app", "title", "text", "time", "source", "test")


def parse_payload(body: bytes, content_type: str, query: str) -> dict:
    """Best effort: never raises, always returns something worth storing."""
    record: dict = {}
    text = body.decode("utf-8", errors="replace")
    if text.strip():
        parsed = None
        if "json" in content_type or text.lstrip().startswith("{"):
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = None
        if parsed is None and "=" in text and "form" in content_type:
            parsed = {k: v[-1] for k, v in parse_qs(text, keep_blank_values=True).items()}
        if isinstance(parsed, dict):
            record.update({k: str(parsed[k]) for k in FIELDS if k in parsed})
        else:
            record["raw"] = text
    for k, v in parse_qs(query, keep_blank_values=True).items():
        if k in FIELDS and k not in record:
            record[k] = v[-1]
    return record


class CaptureStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def append(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            if self.path.exists() and self.path.stat().st_size > MAX_FILE:
                raise OSError("capture file is full")
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def make_handler(token: str, store: CaptureStore):
    class Handler(BaseHTTPRequestHandler):
        server_version = "capture"
        sys_version = ""

        def _reply(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            if code >= 400:
                self.close_connection = True  # unread request body must not be parsed as a next request
            try:
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # client/proxy already hung up (e.g. after a rejected oversized body)

        def do_GET(self):
            self._reply(404, {"ok": False})

        def do_POST(self):
            url = urlsplit(self.path)
            if url.path != PATH:
                return self._reply(404, {"ok": False})
            if not hmac.compare_digest(self.headers.get(TOKEN_HEADER, ""), token):
                log.warning("Rejected request with a missing/wrong token")
                return self._reply(401, {"ok": False})
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0 or length > MAX_BODY:
                return self._reply(413, {"ok": False})
            body = self.rfile.read(length) if length else b""
            record = parse_payload(body, self.headers.get("Content-Type", ""), url.query)
            record["received_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            try:
                store.append(record)
            except OSError as exc:
                log.error("Could not store notification: %s", exc)
                return self._reply(507, {"ok": False})
            # Log only metadata; the text can contain balances and account numbers.
            log.info("Captured: app=%r test=%r text_len=%d", record.get("app"), record.get("test"),
                     len(record.get("text", record.get("raw", ""))))
            self._reply(200, {"ok": True})

        def log_message(self, fmt, *args):  # default access log would go to stderr unfiltered
            pass

    return Handler


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    env = {**dotenv_values(ROOT / ".env"), **os.environ}
    token = (env.get("WEBHOOK_TOKEN") or "").strip()
    if len(token) < 32:
        raise SystemExit("WEBHOOK_TOKEN missing or shorter than 32 characters in .env")
    port = int(env.get("CAPTURE_PORT") or 8081)
    store = CaptureStore(ROOT / "data" / "notifications.jsonl")
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(token, store))
    log.info("Capture webhook listening on 127.0.0.1:%d%s", port, PATH)
    server.serve_forever()


if __name__ == "__main__":
    main()
