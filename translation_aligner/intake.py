"""Deterministic filename pairing and main-body extraction."""
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath
from zipfile import ZipFile, BadZipFile
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass(frozen=True)
class Pair:
    pair_id: str
    source: str
    target: str


@dataclass(frozen=True)
class Block:
    position: str
    text: str


def pair_files(names: list[str]) -> tuple[list[Pair], list[str]]:
    """Pair case-insensitively as on Windows, rejecting ambiguous names."""
    lookup: dict[str, str] = {}
    problems = []
    ambiguous = set()
    for name in names:
        if PurePath(name).name != name or "/" in name or "\\" in name:
            problems.append(f"Upload a basename only: {name}")
            continue
        if not name.lower().endswith(".docx") or name.startswith("~$"):
            problems.append(f"Not an SOP DOCX: {name}")
            continue
        key = name.casefold()
        if key in lookup:
            ambiguous.add(key)
            problems.append(f"Duplicate filename: {name}")
        lookup[key] = name
    pairs, used = [], set()
    for key in sorted(lookup):
        if key.endswith("-en.docx"):
            continue
        target = key[:-5] + "-en.docx"
        if key in ambiguous or target in ambiguous:
            used.update((key, target))
            continue
        if target in lookup:
            pairs.append(Pair(lookup[key][:-5], lookup[key], lookup[target]))
            used.update((key, target))
    for key in sorted(lookup.keys() - used - ambiguous):
        problems.append(f"Unpaired document: {lookup[key]}")
    return pairs, problems


def extract_body(data: bytes) -> list[Block]:
    """Read only document.xml body, preserving paragraph/table XML order.

    Includes inserted revisions; excludes deleted/moved-from revisions, comments,
    document headers/footers and drawing/textbox content. Limits expanded XML.
    Positions identify original XML paragraphs, not generated sentence numbers.
    """
    try:
        with ZipFile(BytesIO(data)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > 32 * 1024 * 1024:
                raise ValueError("Document body exceeds the 32 MB XML limit.")
            xml = archive.read(info)
    except (BadZipFile, KeyError) as exc:
        raise ValueError("Not a readable Word DOCX document.") from exc
    if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise ValueError("XML entity declarations are not supported.")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError("Invalid Word document XML.") from exc
    body = root.find(W + "body")
    if body is None:
        raise ValueError("Word document has no main body.")
    excluded = {W + tag for tag in ("del", "moveFrom", "drawing", "pict", "txbxContent")}

    def walk(node):
        if node.tag in excluded:
            return
        yield node
        for child in node:
            yield from walk(child)

    result = []
    for number, paragraph in enumerate(n for n in walk(body) if n.tag == W + "p"):
        parts = []
        for node in walk(paragraph):
            if node.tag == W + "t":
                parts.append(node.text or "")
            elif node.tag in (W + "tab", W + "br", W + "cr"):
                parts.append(" ")
        text = "".join(parts).strip()
        if text:
            result.append(Block(f"body.p{number + 1}", text))
    return result
