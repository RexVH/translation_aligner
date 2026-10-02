import json

import httpx
import pytest

from translation_aligner.systran import SystranError, probe, connection_hint


def test_probe_headers_directions_and_redaction():
    requests = []

    def handle(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Key secret-value"
        assert "secret-value" not in str(request.url)
        payload = json.loads(request.content)
        assert payload["withAnnotations"] and payload["withSource"]
        return httpx.Response(200, json={"outputs": [{"source": "source", "output": "target"}], "echo": "secret-value"})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = probe("secret-value", "https://api.example.test", client)
    assert list(result["responses"]) == ["fr-en", "en-fr"]
    assert [json.loads(r.content)["source"] for r in requests] == ["fr", "en"]
    assert "secret-value" not in json.dumps(result)


@pytest.mark.parametrize("status,payload", [(401, {}), (429, {}), (200, {"error": {"message": "private-server-detail"}}),
                                          (200, {"outputs": []}), (200, []),
                                          (200, {"outputs": [{"output": "no source"}]})])
def test_errors_are_actionable_without_server_body(status, payload):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status, json=payload))) as client:
        with pytest.raises(SystranError) as error:
            probe("secret-value", "https://api.example.test", client)
    assert "private-server-detail" not in str(error.value)
    assert "secret-value" not in str(error.value)


@pytest.mark.parametrize("url", ["http://api.test", "https://key@api.test", "https://api.test?key=x"])
def test_bad_endpoints_rejected_before_request(url):
    with pytest.raises(SystranError):
        probe("secret-value", url)


@pytest.mark.parametrize("error,expected", [
    (httpx.ConnectError("[WinError 10013] secret-value"), "10013"),
    (httpx.ConnectError("CERTIFICATE_VERIFY_FAILED secret-value"), "TLS"),
    (httpx.ReadTimeout("secret-value"), "timed out"),
    (httpx.ProxyError("secret-value"), "proxy"),
    (httpx.ConnectError("secret-value"), "DNS"),
])
def test_connection_diagnostics_do_not_leak_exception_text(error, expected):
    message = connection_hint(error)
    assert expected in message
    assert "secret-value" not in message
