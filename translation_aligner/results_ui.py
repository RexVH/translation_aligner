"""Readable review of accepted and rejected candidate alignments."""
import json
from pathlib import Path

import streamlit as st

from .review import METHODS, rejection_reasons
from .exports import export_run, resource_bundle


def render_results(result, path):
    run_id=result['run_id']
    settings=result.get('settings',{})
    rows=result['alignments']
    st.subheader(result['pair']['pair_id'])
    st.caption(f"{METHODS.get(result['backend'],result['backend'])} · {result.get('model','Model not recorded')}")
    counts={status:sum(row['status']==status for row in rows) for status in ('aligned','rejected','unmatched')}
    for column,(label,status) in zip(st.columns(3),[('Accepted','aligned'),('Rejected','rejected'),('Unmatched','unmatched')]):
        column.metric(label,counts[status])
    st.caption('Rejected means the proposed pairing failed a check. It does not necessarily mean the expert translation is wrong. Unmatched means no counterpart was selected.')
    options=['Rejected','Unmatched','Accepted','All']
    selection=st.selectbox('Show alignments',options,index=0 if counts['rejected'] else 3,key=run_id+'-filter')
    status={'Rejected':'rejected','Unmatched':'unmatched','Accepted':'aligned'}.get(selection)
    selected=[(i,row) for i,row in enumerate(rows) if status is None or row['status']==status]
    if not selected:
        st.info(f'No {selection.lower()} alignments in this run.')
    else:
        table=[]
        for i,row in selected:
            table.append({'Row':i+1,'Decision':row['status'].capitalize(),
                          'Reason': ' '.join(rejection_reasons(row,settings)) or 'Passed alignment checks',
                          'French source':row['fr'],'Expert English':row['en']})
        st.dataframe(table,hide_index=True)
        chosen=st.selectbox('Inspect a pairing',[i for i,_ in selected],
                            format_func=lambda i:f"Row {i+1} — {rows[i]['fr'][:65] or rows[i]['en'][:65]}",key=run_id+'-row-'+selection)
        row=rows[chosen]
        with st.container(border=True):
            for reason in rejection_reasons(row,settings):
                st.warning(reason)
            if row['status']=='aligned':
                st.success('Accepted by the alignment checks. Export classification and conflict checks are separate.')
            left,right=st.columns(2)
            left.markdown('**Original French**')
            left.text(row['fr'] or '(No source segment)')
            right.markdown('**Expert English**')
            right.text(row['en'] or '(No target segment)')
            st.caption(f"Method: {METHODS.get(row['method'],row['method'])} · Group: {len(row.get('fr_ids',row.get('fr_indices',[])))} FR → {len(row.get('en_ids',row.get('en_indices',[])))} EN segments")
            cosine=row.get('cosine')
            if cosine is not None:
                threshold=row.get('semantic_threshold',settings.get('semantic_floor',.72))
                st.text(f'Semantic similarity: {cosine:.3f} / required minimum: {threshold:.3f}')
            with st.expander('Translation evidence and segment IDs'):
                st.markdown('**Systran EN from the French source**')
                st.text(row.get('mt_en','Not recorded'))
                st.markdown('**Systran FR from the expert English**')
                st.text(row.get('mt_fr','Not recorded'))
                st.json({key:row.get(key) for key in ('fr_score','en_score','conservative_score','fr_ids','en_ids')})
    with st.expander('Saved run and alignment download'):
        st.caption(str(path))
        st.caption('Changing the model or thresholds above affects the next run, not these saved results.')
        st.download_button('Download alignment and provenance',json.dumps(result,ensure_ascii=False,indent=2),
                           file_name=f"{result['pair']['pair_id']}-alignment.json",mime='application/json',key=run_id+'-json')
    st.markdown('**Dictionary and translation memory**')
    st.caption('Accepted sentences → TMX. Accepted short expressions and observed seed terminology → dictionary. Conflicting translations are excluded. Normalization rules are not generated.')
    export_key=run_id+'-export'
    # A run produced before exports were implemented can be exported without API calls.
    if st.button('Generate exports and update master',key=run_id+'-generate'):
        try:
            st.session_state[export_key]=export_run(result)
        except (OSError,ValueError,TimeoutError) as exc:
            st.error(f'Export failed: {exc}')
    exported=st.session_state.get(export_key) or result.get('resource_export')
    if exported:
        st.caption(f"Master version: {exported['version']}. This is the snapshot associated with this export, not necessarily the latest master.")
        summary=exported['counts']
        st.text(f"Master: {summary['tm_entries']} TM entries · {summary['dictionary_entries']} dictionary entries · {summary['conflicts']} unresolved conflicts")
        if summary['conflicts']:
            st.warning('Conflicting FR → EN translations were excluded from this master. Review conflicts.json in the download; prior master versions remain unchanged.')
        pair_manifest=Path(exported['pair_folder'])/'manifest.json'
        if pair_manifest.exists():
            pair_counts=json.loads(pair_manifest.read_text(encoding='utf-8'))['counts']
            st.text(f"This pair: {pair_counts['tm_entries']} TM entries · {pair_counts['dictionary_entries']} dictionary entries · {pair_counts['conflicts']} conflicts")
        st.download_button('Download pair and master resources (ZIP)',resource_bundle(exported),
                           file_name=f"resources-{exported['version']}.zip",mime='application/zip',key=run_id+'-zip')
