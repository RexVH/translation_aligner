import json
from pathlib import Path

from translation_aligner.intake import extract_body, pair_files


def test_sample_pair_matches_manifest_and_excludes_headers():
    folder = Path(__file__).parents[1] / "samples"
    pairs, problems = pair_files([p.name for p in folder.glob("*.docx")])
    assert not problems and len(pairs) == 1
    manifest = json.loads((folder / "expected_alignment.json").read_text(encoding="utf-8"))
    for lang, filename in (("fr", pairs[0].source), ("en", pairs[0].target)):
        blocks = extract_body((folder / filename).read_bytes())
        positions = {block.position: block.text for block in blocks}
        for case in manifest["cases"]:
            assert [positions[pos] for pos in case[lang + "_positions"]] == case[lang]
        assert all("EXCLUDE" not in block.text and "EXCLURE" not in block.text for block in blocks)
        for term in manifest["dictionary_pairs"]:
            assert term[lang] in positions.values()
    categories = {case["category"] for case in manifest["cases"]}
    assert {"exact_candidate", "fuzzy", "semantic", "one_to_many", "many_to_one",
            "addition", "omission", "translation_conflict", "reject_numeric_mismatch",
            "reject_negation_mismatch"} <= categories
