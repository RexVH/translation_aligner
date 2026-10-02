"""Local setup and intake screen. Run with streamlit run streamlit_app.py."""
import json
import os
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

import streamlit as st

from translation_aligner.intake import extract_body, pair_files
from translation_aligner.systran import SystranError, probe
from translation_aligner.alignment import Settings
from translation_aligner.pipeline import run_pair
from translation_aligner.semantic import SemanticAligner
from translation_aligner.models import MODELS
from translation_aligner.results_ui import render_results

st.set_page_config(page_title="Translation aligner", page_icon=":material/translate:")
st.title("Translation aligner")
st.caption("French SOPs · Expert English translations · Local development")
st.caption("Align document pairs, inspect decisions, and export dictionary and translation-memory resources.")
st.session_state.setdefault("probe_result", None)
st.session_state.setdefault("alignment_results", [])


@st.cache_resource(max_entries=1)
def load_semantic(backend, model_key):
    return SemanticAligner(backend, model_key=model_key)

with st.container(border=True):
    st.subheader("1. Connect Systran")
    st.markdown("Test two short synthetic passages in French and English. Your key is kept in this session and is not written to project files.")
    with st.form("connection"):
        endpoint = st.text_input("API base URL", value=os.getenv("SYSTRAN_BASE_URL", "https://api-translate.systran.net"))
        entered_key = st.text_input("API key", type="password", help="Leave blank to use SYSTRAN_API_KEY from the environment.")
        submitted = st.form_submit_button("Test with synthetic text", type="primary")
    if submitted:
        st.session_state.probe_result = None
        try:
            with st.spinner("Testing FR → EN and EN → FR…"):
                result = probe(entered_key or os.getenv("SYSTRAN_API_KEY", ""), endpoint)
            st.session_state.probe_result = result
        except SystranError as exc:
            st.error(str(exc))
    if st.session_state.probe_result:
        st.success("Both translation requests succeeded.")
        st.caption("Save the synthetic response locally so the segment parser can be checked against your service. No SOP content is included.")
        if st.button("Save synthetic response for development"):
            folder = Path("local_data/probes")
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"systran-{uuid4().hex}.json"
            path.write_text(json.dumps(st.session_state.probe_result, ensure_ascii=False, indent=2), encoding="utf-8")
            st.success(f"Saved {path.as_posix()}")

with st.container(border=True):
    st.subheader("2. Validate document pairs")
    st.markdown("Upload `name.docx` and `name-EN.docx`. Files stay local; this step makes no translation requests.")
    uploads = st.file_uploader("Word documents", type=["docx"], accept_multiple_files=True)
    if uploads:
        total_bytes = sum(upload.size for upload in uploads)
        if total_bytes > 256 * 1024 * 1024:
            st.error("This laptop intake screen supports at most 256 MB per batch.")
        else:
            pairs, problems = pair_files([upload.name for upload in uploads])
            st.metric("Matched document pairs", len(pairs))
            if pairs:
                st.dataframe([asdict(pair) for pair in pairs], hide_index=True)
            for problem in problems:
                st.warning(problem)
            if st.button("Inspect main bodies", disabled=not pairs or bool(problems)):
                by_name = {upload.name: upload for upload in uploads}
                progress = st.progress(0, text="Reading main-body paragraphs and tables")
                rows = []
                for index, pair in enumerate(pairs):
                    for lang, name in (("FR", pair.source), ("EN", pair.target)):
                        try:
                            blocks = extract_body(by_name[name].getvalue())
                            rows.append({"document": name, "language": lang, "paragraphs": len(blocks),
                                         "characters": sum(len(block.text) for block in blocks)})
                        except ValueError as exc:
                            st.error(f"{name}: {exc}")
                    progress.progress((index + 1) / len(pairs))
                st.dataframe(rows, hide_index=True)

            st.subheader("3. Align document pairs")
            st.caption("Run alignment sends main-body text to the configured Systran endpoint in both directions. Completed paragraph translations are cached locally for retries.")
            backend_label = st.selectbox("Semantic alignment backend", ["VecAlign", "Portable semantic DP (CPU; different algorithm)"],
                                         help="VecAlign requires Microsoft C++ Build Tools for installation on Windows. The portable backend uses grouped-sentence dynamic programming.")
            backend = 'vecalign' if backend_label == 'VecAlign' else 'portable_dp'
            model_key=st.selectbox('Embedding model',list(MODELS),format_func=lambda key:MODELS[key]['label'],key='embedding_model')
            st.caption(MODELS[model_key]['description'])
            st.caption('All options run locally on CPU. A new model downloads on first use. Similarity scores differ between models; validate the threshold when comparing them.')
            with st.expander("Alignment settings"):
                floor = st.slider("Minimum fuzzy score in each direction", 0, 100, 80)
                combined = st.slider("Minimum combined fuzzy score", 0, 100, 88)
                semantic_floor = st.slider("Minimum semantic cosine similarity", 0.0, 1.0, 0.72, 0.01)
                st.caption("Thresholds are provisional; scores are not probabilities. Number and possible negation mismatches are rejected for review.")
            if st.button("Run alignment", type="primary", disabled=not pairs or bool(problems)):
                st.session_state.alignment_results = []
                active_key = entered_key or os.getenv('SYSTRAN_API_KEY','')
                if not active_key.strip():
                    st.error("Enter your API key in step 1 and submit its form before running alignment.")
                else:
                    try:
                        with st.spinner("Loading CPU embeddings (first use downloads the multilingual model)…"):
                            semantic = load_semantic(backend, model_key)
                        by_name = {upload.name: upload for upload in uploads}
                        batch = st.progress(0, text="Starting alignment")
                        for index,pair in enumerate(pairs):
                            def report(value, message):
                                batch.progress((index+value)/len(pairs), text=f"{pair.pair_id}: {message}")
                            result,path = run_pair(pair,by_name[pair.source].getvalue(),by_name[pair.target].getvalue(),
                                                   active_key,endpoint,semantic,Settings(fuzzy_floor=floor,fuzzy_score=combined,semantic_floor=semantic_floor),report)
                            st.session_state.alignment_results.append((result,str(path)))
                        st.success("Alignment complete. Results are saved locally.")
                    except (SystranError, ValueError, RuntimeError, OSError) as exc:
                        # Model/download exceptions can include URLs; never display credentials.
                        st.error(str(exc).replace(active_key, '[REDACTED]'))

with st.expander('Open a saved alignment run'):
    saved_paths=sorted(Path('local_data/runs').glob('*/alignment.json'),reverse=True)
    if saved_paths:
        saved=st.selectbox('Saved run',saved_paths,format_func=lambda p:p.parent.name)
        if st.button('Load saved results'):
            st.session_state.alignment_results=[(json.loads(saved.read_text(encoding='utf-8')),str(saved))]
    else:
        st.caption('No saved runs yet.')

if st.session_state.alignment_results:
    st.subheader("Alignment results")
    for result,path in st.session_state.alignment_results:
        render_results(result,path)
