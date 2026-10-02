# Synthetic SOP pair

Upload `SOP_DEMO_001.docx` as FR and `SOP_DEMO_001-EN.docx` as the expert-side EN.
Both files are AI-authored fictional testing material, not validated manufacturing
instructions or human-expert translations. The English document models an edited
professional translation and intentionally contains a few defects to test rejection.

## Expected behavior

`expected_alignment.json` maps source and target text to actual body paragraph
positions. These are document positions, not Systran sentence IDs. Alignment stage
labels express test intentions: live Systran wording and segmentation can change
whether a passage is handled by exact matching, RapidFuzz, or VecAlign.

- Simple batch-number/date instructions: exact-match candidates.
- Signature/attachment/scope passages: fuzzy-match candidates.
- Traceability and document-hold passages: semantic/VecAlign candidates.
- Attachment check: one FR paragraph to two EN paragraphs.
- Discrepancy notification: two FR paragraphs to one EN paragraph.
- Grey-folder instruction exists only in FR; electronic-reference instruction only
  in EN. Leave them unmatched, not force-aligned to adjacent text.
- `Enregistrer le résultat.` appears twice. Use document order and surrounding
  anchors; retain both occurrences in provenance and deduplicate identical exports.
- `15 entrées` versus `50 entries`, and `Ne pas archiver` versus `Archive`, are
  deliberate translation defects. Exclude them from TM/dictionary export even if
  an aligner finds a high lexical or semantic score.
- `Vérifier le dossier.` has two different EN targets. Report a conflict and exclude
  the unresolved entry from generated resources; do not overwrite either candidate.
- A terminology table provides five unambiguous pharma/documentation term pairs.
  Codes T01–T05 are structural labels, not dictionary candidates.
- Headers/footers contain explicit exclusion markers; none should reach extraction
  or exports. Body section headings should be retained.
- Orionex and Belrive are fictional names. Preserve their spellings; this pair
  provides no evidence for a normalization rule.

The app now supports segmentation and alignment with numeric/negation review
flags and dictionary/TMX exports with versioned masters. A separate controlled MT
fixture will be needed for deterministic tests of all three alignment stages.

Regenerate with `python scripts/generate_samples.py` after installing python-docx.
