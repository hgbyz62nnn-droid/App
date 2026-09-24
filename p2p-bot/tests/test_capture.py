import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from p2pbot.capture import MAX_BODY, PATH, CaptureStore, make_handler, parse_payload

TOKEN = "t" * 40


@pytest.fixture
def server(tmp_path):
    store = CaptureStore(tmp_path / "notifications.jsonl")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(TOKEN, store))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", store.path
    srv.shutdown()


def post(base, path=PATH, body=b"", ctype="application/json", token=TOKEN):
    req = urllib.request.Request(base + path, data=body, method="POST")
    req.add_header("Content-Type", ctype)
    if token is not None:
        req.add_header("X-Webhook-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def lines(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def test_json_is_stored(server):
    base, path = server
    body = json.dumps({"app": "InstaPay", "title": "تم الاستلام", "text": "استلمت 500 جنيه", "time": "10:01"})
    assert post(base, body=body.encode()) == 200
    [rec] = lines(path)
    assert rec["app"] == "InstaPay" and rec["text"] == "استلمت 500 جنيه" and "received_at" in rec


def test_form_and_query_params(server):
    base, path = server
    assert post(base, body="app=Vodafone+Cash&text=a%22b%26c".encode(), ctype="application/x-www-form-urlencoded") == 200
    assert post(base, path=PATH + "?app=Bank&text=hello%20%22x%22&test=1", body=b"") == 200
    a, b = lines(path)
    assert a == {**a, "app": "Vodafone Cash", "text": 'a"b&c'}
    assert b["app"] == "Bank" and b["text"] == 'hello "x"' and b["test"] == "1"


def test_broken_json_is_kept_raw(server):
    # MacroDroid pastes text with quotes straight into a JSON template -> invalid JSON. Keep it anyway.
    base, path = server
    assert post(base, body=b'{"app":"InstaPay","text":"he said "hi""}') == 200
    assert lines(path)[0]["raw"].startswith('{"app"')


@pytest.mark.parametrize("token", [None, "", "wrong", TOKEN + "x"])
def test_bad_token_rejected_and_nothing_stored(server, token):
    base, path = server
    assert post(base, body=b'{"app":"x"}', token=token) == 401
    assert lines(path) == []


def test_wrong_path_and_get_are_404(server):
    base, path = server
    assert post(base, path="/other", body=b"{}") == 404
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(base + PATH, timeout=5)
    assert e.value.code == 404


def test_oversized_body_rejected(server):
    base, path = server
    assert post(base, body=b"x" * (MAX_BODY + 1)) == 413
    assert lines(path) == []


def test_file_is_private(server):
    base, path = server
    post(base, body=b'{"app":"x"}')
    assert (path.stat().st_mode & 0o777) == 0o600


def test_parse_payload_never_raises():
    assert parse_payload(b"\xff\xfe", "", "") == {"raw": "��"}
    assert parse_payload(b"", "", "") == {}
