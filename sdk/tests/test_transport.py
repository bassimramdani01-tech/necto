import urllib.error

from necto_sdk.transport import HttpTransport


class FakeResponse:
    def __init__(self, body=b'{"ok": true}'):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _http_error(url, code):
    return urllib.error.HTTPError(url, code, "boom", {}, None)


def test_retries_server_errors_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(request, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_error(request.full_url, 503)
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    transport = HttpTransport("http://example.invalid", attempts=3, backoff=0)
    transport.append_events("run-1", [{"type": "handoff"}])
    assert calls["n"] == 2


def test_gives_up_after_attempts(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(request, timeout=None):
        calls["n"] += 1
        raise _http_error(request.full_url, 500)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    transport = HttpTransport("http://example.invalid", attempts=3, backoff=0)
    transport.append_events("run-1", [{"type": "handoff"}])
    assert calls["n"] == 3


def test_does_not_retry_client_errors(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(request, timeout=None):
        calls["n"] += 1
        raise _http_error(request.full_url, 422)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    transport = HttpTransport("http://example.invalid", attempts=3, backoff=0)
    transport.append_events("run-1", [{"type": "handoff"}])
    assert calls["n"] == 1


def test_network_errors_are_retried(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(request, timeout=None):
        calls["n"] += 1
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    transport = HttpTransport("http://example.invalid", attempts=2, backoff=0)
    transport.append_events("run-1", [{"type": "handoff"}])
    assert calls["n"] == 2


def test_create_run_returns_id(monkeypatch):
    def fake_urlopen(request, timeout=None):
        return FakeResponse(b'{"id": "abc-123"}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    transport = HttpTransport("http://example.invalid")
    assert transport.create_run("n", {}) == "abc-123"


def test_blank_run_id_skips_request(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(request, timeout=None):
        calls["n"] += 1
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    transport = HttpTransport("http://example.invalid")
    transport.append_events("", [{"type": "handoff"}])
    transport.finish_run("", "ok", None)
    assert calls["n"] == 0
