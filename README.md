# Translation aligner

Local development of an auditable French/English SOP alignment pipeline.
The app provides Systran segmentation, exact/fuzzy/semantic alignment and saved
alignment provenance, dictionary/TMX exports, and versioned master resources.
See [the agreed design](docs/design.md) for decisions and remaining work.

## Run on Windows

Python 3.12 is recommended. From PowerShell in this repository:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

If `.venv` is already installed, only the last command is necessary.
Open http://127.0.0.1:8501. Enter the API key in the password field and click
**Test with synthetic text**. This makes two short translation requests, one per
direction. It does not send any uploaded SOP. Successful responses can be saved
under ignored `local_data/probes/` for annotation-schema verification.

Alternatively set `SYSTRAN_API_KEY` in the environment; the UI uses it when its
key field is blank. Use `SYSTRAN_BASE_URL` for an internal HTTPS endpoint.
Credentials are sent in an Authorization header, never URL query parameters.
Do not commit keys or paste them into chat. The UI key is session-only; restarting
the app requires entering it again. A user-run bidirectional API probe succeeded;
the annotation parser has been verified against that response.

## Sample documents

Upload `samples/SOP_DEMO_001.docx` and `samples/SOP_DEMO_001-EN.docx` together.
See [the fixture guide](samples/README.md) for expected correspondences, intentional
translation defects, and limitations. These are synthetic test documents.

## Run alignment

1. Enter the API key and submit the connection form.
2. Upload matching FR and EN files.
3. Choose the semantic backend and embedding model, then click **Run alignment**.

**Portable semantic DP** is ready on the current Windows laptop. It uses a pinned
multilingual sentence model on CPU and global dynamic programming with grouped
sentences. It is a different algorithm from VecAlign and is labeled accordingly.
Each selected model downloads once and then uses its own local embedding cache.
Documents are never sent to a remote embedding service.

The model dropdown offers these pinned alternatives (all run on CPU):

- [Multilingual MiniLM](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2): compact default, tested locally.
- [Multilingual MPNet](https://huggingface.co/sentence-transformers/paraphrase-multilingual-mpnet-base-v2): larger paraphrase model.
- [LaBSE](https://huggingface.co/sentence-transformers/LaBSE): cross-language sentence matching.
- [Multilingual DistilUSE](https://huggingface.co/sentence-transformers/distiluse-base-multilingual-cased-v2): alternative multilingual baseline.

Additional model weights download only when selected for a run. Their local loader
and cache selection are unit-tested; only MiniLM has been exercised with actual
weights here. Thresholds are model-dependent; a larger model is not automatically
better for these SOPs. Saved results retain the actual selected model and revision.

**VecAlign** is integrated but needs a native compiler to install on Windows.
Install Microsoft C++ Build Tools with Desktop development with C++, then run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-vecalign.txt
```

VecAlign installation failed here because the C++ compiler is absent; that backend
has not been runtime-tested on this machine. Its missing dependency stops the run
before API calls; it never silently switches algorithms.

Per-paragraph Systran calls preserve body positions and cache validated responses
under `local_data/translations/`. Cache identity includes endpoint, directions,
profile and text. To deliberately refresh translations after a server model change,
use a separate local_data root or archive the translation cache first. Saved raw
responses retain server route metadata. No automatic paid-request retries occur.

Results persist in `local_data/runs/<run-id>/alignment.json`, with original and MT
segments, IDs, input hashes, scores, model revision and settings. The UI preserves
results across reruns and provides a JSON download. Previously completed pairs
remain saved if a later pair fails. Rerunning reuses cached translations but creates
a new alignment run. Exact anchors must be unambiguous and noncrossing. Fuzzy
matching requires both directional floors and uses 75% of the weaker score plus
25% of the stronger score. Residual intervals are aligned separately.

Thresholds are provisional, not calibrated probabilities. Numeric checks and
negation heuristics flag obvious defects but do not establish translation safety.
Semantic encoders have finite context windows; long grouped passages can lose
detail. Inspect rejections and unmatched segments before downstream use.

Headless equivalent (set SYSTRAN_API_KEY first):

```powershell
.\.venv\Scripts\python.exe -m translation_aligner align samples --backend portable_dp
```

Add `--model labse`, `--model mpnet`, or `--model distiluse` to compare models.

## Review decisions and export resources

Results open on **Rejected** when any exist. Reasons include the actual semantic
score and required threshold, differing numbers, and possible negation mismatches.
Select a row to read complete FR/EN text side by side and expand its MT evidence.
Legacy saved runs get inferred score-threshold explanations without rerunning MT.
Use **Open a saved alignment run** to restore results after a browser refresh.

New alignment runs automatically generate resources. For an older run, click
**Generate exports and update master**; this needs no API calls or embedding model.
Download the ZIP containing `pair/` and `master/` folders:

- `translation_memory.tmx`: TMX 1.4, original FR and expert EN sentence pairs.
- `dictionary.txt`: UTF-8 tab-delimited Systran user dictionary with required headers.
- `entries.json`: accepted entries, extraction evidence and source provenance.
- `conflicts.json`: all competing expert translations for an unresolved source.
- `excluded.json`: skipped rows/reasons (per-pair); master exclusions are traced through pair artifacts.
- `manifest.json`: counts, model/run information for pairs; parent version and added/removed entries for masters.

Only accepted, unflagged rows contribute. Sentence detection currently requires
terminal punctuation and at least three words. Dictionary extraction uses short
non-sentence expressions plus a small seed lexicon whose FR/EN terms must actually
occur in the aligned original/expert text. This is an initial heuristic, not a
general pharma terminology extractor or linguistic POS classifier. Review the
result before importing; arbitrary sub-sentence terminology discovery remains
future work. No normalization rules are inferred. Systran import itself still
needs testing against your installation.

Per-pair snapshots reside in `local_data/resources/pairs/`; immutable master
versions reside in `local_data/resources/masters/`. `latest.json` points at the
most recently published master. A filesystem lock serializes publication, and the
pointer updates atomically after files are complete. Re-exporting the active run
is idempotent. Reprocessing a pair replaces its contribution in a new snapshot.
Conflicting entries are removed from the NEW master until resolved; prior master
files remain intact. Expert resolution import is not implemented yet; conflict
reports retain all choices for review. Manual edits to imported Systran resources
are not automatically synchronized back into this project's master history.

Export an existing saved run from the CLI:

```powershell
.\.venv\Scripts\python.exe -m translation_aligner export local_data/runs/RUN_ID/alignment.json
```

## Headless commands

```powershell
.\.venv\Scripts\python.exe -m translation_aligner inspect C:\path\to\documents
.\.venv\Scripts\python.exe -m translation_aligner probe
.\.venv\Scripts\python.exe -m pytest -q
```

Probe uses the environment key and refuses to overwrite an existing diagnostic
output; supply `--output` to select another path. Intake expects `name.docx` and
`name-EN.docx`, reports orphans/duplicates, and reads main-body paragraphs/tables
without transmitting their contents. It excludes header/footer parts, comments,
deleted revisions, and drawing text. Word automatic list labels are not currently
expanded. The UI limits individual files to 20 MB and the batch to 256 MB.
