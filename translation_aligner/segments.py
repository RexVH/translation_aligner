"""Systran annotation adapter, verified against the saved public API response."""
from dataclasses import dataclass
import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit

import httpx

from .systran import SystranError, connection_hint


@dataclass(frozen=True)
class Segment:
    id: str
    position: str
    text: str
    mt: str


def compact(text):
    return re.sub(r"\s+", "", text)


def parse_output(payload, position, original, source, target):
    try:
        outputs = payload["outputs"]
        if len(outputs) != 1 or outputs[0].get("error"):
            raise ValueError()
        documents = outputs[0]["output"]["documents"]
        segments = []
        for document in documents:
            if document["src_lang"] != source or document["tgt_lang"] != target:
                raise ValueError()
            for unit in document["trans_units"]:
                for sentence in unit["sentences"]:
                    alternatives = sentence["alt_transes"]
                    # No undocumented selection among competing translations.
                    if len(alternatives) != 1:
                        raise ValueError()
                    text = sentence["source"]["text"]
                    mt = alternatives[0]["target"]["text"]
                    if not text.strip() or not mt.strip():
                        raise ValueError()
                    segments.append(Segment(f"{position}:{unit['id']}:{sentence['id']}", position, text.strip(), mt.strip()))
        if not segments or len({s.id for s in segments}) != len(segments):
            raise ValueError()
        if compact("".join(s.text for s in segments)) != compact(original):
            raise ValueError()
        return segments
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise SystranError(f"Unrecognized or incomplete Systran annotations at {position}; no local segmentation was substituted.") from exc


def translate_blocks(blocks, source, target, key, endpoint, cache, progress, profile=None):
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SystranError("Use an HTTPS API base URL without credentials, query, or fragment.")
    if not key.strip():
        raise SystranError("Enter an API key before running alignment.")
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    segments, response_hashes = [], []
    with httpx.Client(timeout=httpx.Timeout(120, connect=15), follow_redirects=False) as client:
        for index, block in enumerate(blocks):
            identity = json.dumps([endpoint.rstrip('/'), source, target, profile, block.text, "annotations-v1"], ensure_ascii=False)
            digest = hashlib.sha256(identity.encode()).hexdigest()
            path = cache / f"{digest}.json"
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
            else:
                request = {"input": block.text, "source": source, "target": target,
                           "format": "text/plain", "withSource": True, "withAnnotations": True, "withInfo": True}
                if profile:
                    request["profile"] = profile
                try:
                    response = client.post(endpoint.rstrip('/') + '/translation/text/translate',
                                           headers={"Authorization": "Key " + key.strip()}, json=request)
                except httpx.HTTPError as exc:
                    raise SystranError(connection_hint(exc)) from None
                if response.status_code != 200:
                    raise SystranError(f"{source}→{target}: HTTP {response.status_code} at {block.position}. Completed paragraphs are cached; retry later.")
                try:
                    payload = response.json()
                except ValueError:
                    raise SystranError("Systran returned a non-JSON response.") from None
                parse_output(payload, block.position, block.text, source, target)
                serialized = json.dumps(payload, ensure_ascii=False).replace(key.strip(), "[REDACTED]")
                temporary = path.with_suffix('.'+uuid4().hex+'.tmp')
                temporary.write_text(serialized, encoding="utf-8")
                temporary.replace(path)
            segments.extend(parse_output(payload, block.position, block.text, source, target))
            response_hashes.append(digest)
            progress((index + 1) / len(blocks), f"{source.upper()} → {target.upper()}: paragraph {index + 1}/{len(blocks)}")
    return segments, response_hashes
