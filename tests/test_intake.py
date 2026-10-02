from io import BytesIO
from zipfile import ZipFile

import pytest

from translation_aligner.intake import extract_body, pair_files


def test_pairing_order_orphans_and_case():
    pairs, problems = pair_files(["B-EN.docx", "b.docx", "a.docx", "a-EN.docx", "lost-EN.docx"])
    assert [p.pair_id for p in pairs] == ["a", "b"]
    assert pairs[1].target == "B-EN.docx"
    assert problems == ["Unpaired document: lost-EN.docx"]


def test_ambiguous_pairs_never_selected():
    pairs, problems = pair_files(["a.docx", "A.docx", "a-EN.docx", "../x.docx"])
    assert not pairs
    assert any("Duplicate" in issue for issue in problems)
    assert any("basename" in issue for issue in problems)


def test_body_table_revision_order_and_exclusions():
    buffer = BytesIO()
    xml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
      <w:p><w:r><w:t>Heading</w:t></w:r></w:p>
      <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Table cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
      <w:p><w:del><w:r><w:delText>Old text</w:delText></w:r></w:del>
        <w:ins><w:r><w:t>New text</w:t></w:r></w:ins>
        <w:r><w:drawing><w:p><w:r><w:t>Hidden drawing</w:t></w:r></w:p></w:drawing></w:r>
      </w:p></w:body></w:document>'''
    with ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", xml)
        archive.writestr("word/header1.xml", "Header must never appear")
        archive.writestr("word/comments.xml", "Comment must never appear")
    blocks = extract_body(buffer.getvalue())
    assert [b.text for b in blocks] == ["Heading", "Table cell", "New text"]
    assert [b.position for b in blocks] == ["body.p1", "body.p2", "body.p3"]


def test_corrupt_document_is_reported():
    with pytest.raises(ValueError, match="DOCX"):
        extract_body(b"not a docx")
