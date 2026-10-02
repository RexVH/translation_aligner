# Translation aligner decisions

## Intended workflow

Run locally on a Windows laptop with 16 GB RAM. All embedding computation uses
CPU; no dependency on the Intel integrated GPU. Process one document pair at a
time initially. Typical documents are ten pages; overnight batches are acceptable.
Streamlit and a CLI will share the same engine. OpenShift deployment is deferred.

Pair `name.docx` (FR) with `name-EN.docx` (expert EN), case-insensitively. Reject
duplicate or ambiguous filenames and report missing partners. Default ordering
is filename order; a future manifest allows an explicit order and evaluation-only
pairs. Preserve originals and record content hashes to detect revisions.

Read only main-body paragraphs and tables, including section headings. Exclude
document headers/footers, comments, deleted revisions, and drawing text. The
initial extractor uses final-view revision semantics (includes insertions).
Explicit numbering stored as Word list metadata is not yet rendered as text.

Translate FR to EN and expert EN to FR. Systran creates sentence boundaries;
retain its segment IDs alongside original body positions. Public documentation
limits annotations to plain text and HTML, so extract body content first.
Do not invent sentence IDs or silently substitute a local segmenter when the
annotation response is unrecognized. Validate the schema with synthetic probes.

## Alignment

1. Normalize Unicode and whitespace conservatively. Preserve numbers, units,
   punctuation that changes meaning, and negation. Compare original FR to MT FR
   and expert EN to MT EN. Use order/context to disambiguate repetitions.
2. RapidFuzz comparisons in both directions: require a floor for the weaker
   direction, then combine scores conservatively. Thresholds are configurable and
   require internal validation. Weak candidates remain available to stage 3.
3. Run actual VecAlign within unmatched intervals bounded by noncrossing anchors.
   Do not concatenate separate residual intervals. Provide local CPU multilingual
   embeddings for individual and consecutive grouped sentences. Support omissions,
   additions and one-to-many/many-to-one alignment. Reject residual weak results.

Record both directional scores, match method, group membership, source locations,
configuration, model version, and rejected candidates. Scores are not calibrated
probabilities. No MT text is used as the expert side of exported resources.

## Resource generation

Full sentences produce TM entries. Extract pharma terms and multiword expressions
from accepted original/expert pairs for the user dictionary. One sentence may
contribute both a TM entry and terms. Automatically include qualifying entries
when there is no conflict; experts can edit resources at the end. Alignment
confidence and terminology-extraction confidence remain separate fields.

Normalization dictionaries are disabled initially. Explicitly approved same-language
variant mappings can be added later. Brand preservation can use do-not-translate
dictionary entries; unusual spelling alone is not evidence for normalization.

Export TMX (documented support: 1.2–1.4) and UTF-8 Systran structured dictionary
text. Validate actual imports against the installed Systran version. Produce no
empty normalization file merely to fill a slot.

Keep candidate translations as a multimap with provenance. Collapse identical
source/target pairs while retaining every occurrence. Conflicting target variants
are excluded from new pair/master exports until resolved, including entries that
were present in a previous master. Prior snapshots remain immutable. Never let
Python dictionary assignment silently select the last observed target.

Expert resolution uses an exported report and imported resolution file, selecting
a target or rejecting the entry. Bind resolutions to the candidate-set fingerprint
so new competing translations invalidate stale decisions. Keep an audit record.

## Version history and evaluation

Every pair creates immutable individual alignment/resource artifacts. Each pair
then produces a new immutable master snapshot containing contributions of all
active pair revisions. Reprocessing replaces that pair's active contribution in
a new snapshot, without deleting old artifacts. Master writes must be atomic and
serialized, even if processing later becomes parallel.

A snapshot records its parent, ordered pair revision IDs, input hashes, algorithm
and model/configuration versions, resource hashes, conflict report, resolutions,
and added/removed entries. A pointer identifies the current completed snapshot.
Restarting a job must not duplicate contributions or publish partial masters.

Reserve a fixed, held-out set of expert-translated documents. Never aggregate their
entries. Compare baseline and each master-backed translation on that same set,
recording the Systran engine/profile/resource versions and evaluation metrics.
Keep alignment-generation MT on a fixed baseline profile to avoid feedback loops.
Human review complements metrics; changed resource counts alone do not measure
translation quality. Real validation data stays internal.

## Development fixtures

Synthetic DOCX pairs and controlled translation responses must cover exact, fuzzy,
semantic, grouped, repeated, conflicting, inserted and omitted text. Live MT may
route examples through different stages. Mock fixtures must be visibly labeled
and never presented as live Systran or actual VecAlign results.

## Current implementation boundary

Implemented: local Streamlit setup, masked API-key entry, synthetic bidirectional
API probe, filename pairing, main-body extraction, CLI diagnostics and tests.
Also available: a synthetic DOCX demonstration pair with an expected-alignment
manifest in `samples/`, reproducible through `scripts/generate_samples.py`.
Implemented next: annotation parser verified against saved responses; exact/fuzzy
anchors; interval-based semantic alignment; CPU MiniLM embeddings; saved JSON
alignment/provenance; Streamlit progress/results and batch CLI. VecAlign adapter
is present but its Windows build requires missing C++ Build Tools. An explicitly
labeled portable global-DP semantic backend is available separately.
Also implemented: selectable pinned multilingual models, explanatory rejection
review, per-pair TMX/dictionary exports and immutable master snapshots. Initial
term extraction uses short-expression heuristics and observed seed terminology;
it is not a general pharma terminology classifier. A saved user-run sample has
been exported successfully. Pending: expert resolution import, broader terminology
extraction, evaluation runner, and controlled MT fixtures. Actual Systran resource
import remains to be validated internally.

## References

- https://docs.systran.net/translateAPI/translation/
- https://docs.systran.net/translate/en/user-guide/customizing-translation/resources-management.html
- https://github.com/thompsonb/vecalign
