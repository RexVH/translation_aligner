"""Small API probe; no assumptions about undocumented annotation schemas."""
from urllib.parse import urlsplit

import httpx


class SystranError(RuntimeError):
    """Safe user-facing errors, without request headers or server response bodies."""


def connection_hint(exc: httpx.HTTPError) -> str:
    """Classify failures without displaying exception text that may contain secrets."""
    chain, seen = [], set()
    current = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__
    if any(getattr(error, "winerror", None) == 10013 or "10013" in str(error) for error in chain):
        return "Windows blocked the outbound connection (10013). Run the app outside the restricted sandbox or check firewall permissions."
    if any("CERTIFICATE_VERIFY_FAILED" in str(error) for error in chain):
        return "TLS certificate verification failed. Configure your organization's trusted CA certificate; keep certificate verification enabled."
    if isinstance(exc, httpx.TimeoutException):
        return "Systran timed out. Check connectivity and server availability before retrying."
    if isinstance(exc, httpx.ProxyError):
        return "The proxy connection failed. Check the HTTPS proxy configuration."
    return "Could not connect to Systran. Check DNS, the API endpoint, and network access."


def probe(api_key: str, base_url: str, client: httpx.Client | None = None) -> dict:
    """Translate synthetic text in both directions and retain annotation responses.

    Caller owns any provided HTTP client. No automatic retries: each request may
    consume translation credits. API keys are sent only in Authorization headers.
    """
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise SystranError("Use an HTTPS API base URL without embedded credentials.")
    if parsed.query or parsed.fragment:
        raise SystranError("The API base URL cannot contain query parameters or fragments.")
    if not api_key.strip():
        raise SystranError("Enter an API key or set SYSTRAN_API_KEY.")
    samples = {
        "fr-en": "Vérifier le numéro de lot. Enregistrer le résultat dans le dossier de fabrication.",
        "en-fr": "Check the batch number. Record the result in the manufacturing record.",
    }
    owned = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(90, connect=15), follow_redirects=False)
    results = {}
    try:
        for direction, text in samples.items():
            source, target = direction.split("-")
            response = client.post(
                base_url.rstrip("/") + "/translation/text/translate",
                headers={"Authorization": "Key " + api_key.strip()},
                json={"input": text, "source": source, "target": target,
                      "format": "text/plain", "withSource": True,
                      "withAnnotations": True, "withInfo": True},
            )
            if response.status_code != 200:
                hint = {401: "Check your API key.", 403: "Check your API subscription and permissions.",
                        429: "Quota or rate limit reached; retry later."}.get(response.status_code, "Check the API endpoint and server availability.")
                raise SystranError(f"{direction}: HTTP {response.status_code}. {hint}")
            try:
                payload = response.json()
            except ValueError as exc:
                raise SystranError(f"{direction}: expected a JSON translation response.") from exc
            if not isinstance(payload, dict):
                raise SystranError(f"{direction}: unexpected response structure.")
            error = payload.get("error")
            if (isinstance(error, dict) and error.get("message")) or (error and not isinstance(error, dict)):
                raise SystranError(f"{direction}: translation service returned an error.")
            outputs = payload.get("outputs")
            if not isinstance(outputs, list) or not outputs or any(
                not isinstance(out, dict) or out.get("error") or "output" not in out or "source" not in out
                for out in outputs
            ):
                raise SystranError(f"{direction}: response lacks successful source/output data.")
            # Never persist a credential even if a gateway echoes it in metadata.
            import json
            results[direction] = json.loads(json.dumps(payload).replace(api_key.strip(), "[REDACTED]"))
    except httpx.HTTPError as exc:
        raise SystranError(connection_hint(exc)) from None
    finally:
        if owned:
            client.close()
    return {"schema_version": 1, "synthetic_only": True, "responses": results}
