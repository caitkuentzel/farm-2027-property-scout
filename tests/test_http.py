import io
import json
from urllib.error import HTTPError, URLError

from farm2027_scout.http import load_json_with_retries


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def test_transient_connection_failure_is_retried() -> None:
    calls = []
    delays = []

    def opener(url, timeout):
        calls.append((url, timeout))
        if len(calls) == 1:
            raise URLError(ConnectionResetError(104, "reset"))
        return Response(json.dumps({"ok": True}).encode())

    result = load_json_with_retries("https://example.test", opener=opener, sleep=delays.append)

    assert result == {"ok": True}
    assert len(calls) == 2
    assert delays == [1.0]


def test_nonretryable_http_error_fails_immediately() -> None:
    calls = []

    def opener(url, timeout):
        calls.append(url)
        raise HTTPError(url, 404, "not found", {}, None)

    try:
        load_json_with_retries("https://example.test", opener=opener, sleep=lambda _: None)
    except HTTPError as error:
        assert error.code == 404
    else:
        raise AssertionError("404 was retried or accepted")
    assert len(calls) == 1
