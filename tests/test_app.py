from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


APP = Path(__file__).parents[1] / "streamlit_app.py"


def test_setup_does_not_call_api_until_requested():
    with patch("translation_aligner.systran.probe") as mock:
        app = AppTest.from_file(str(APP)).run()
        assert not app.exception
        mock.assert_not_called()
        mock.return_value = {"synthetic_only": True, "responses": {"fr-en": {}, "en-fr": {}}}
        app.text_input[1].set_value("test-key")
        app.button[0].click().run()
        assert not app.exception
        assert app.success
        mock.assert_called_once_with("test-key", "https://api-translate.systran.net")


def test_alignment_button_saves_and_displays_results():
    from io import BytesIO
    import streamlit as st
    files=[]
    for name in ['demo.docx','demo-EN.docx']:
        file=BytesIO(b'dummy')
        file.name=name
        file.size=5
        files.append(file)
    result={'run_id':'test-run','pair':{'pair_id':'demo'},'backend':'portable_dp',
            'alignments':[{'fr':'Bonjour','en':'Hello','method':'exact','status':'aligned'}]}
    with patch('streamlit.file_uploader',return_value=files), \
         patch('translation_aligner.semantic.SemanticAligner') as model, \
         patch('translation_aligner.pipeline.run_pair',return_value=(result,Path('local_data/test.json'))) as run:
        app=AppTest.from_file(str(APP)).run()
        app.text_input[1].set_value('test-key')
        app.selectbox[0].select('Portable semantic DP (CPU; different algorithm)')
        app.selectbox(key='embedding_model').set_value('labse')
        next(button for button in app.button if button.label=='Run alignment').click().run()
        assert not app.exception
        assert run.call_count==1
        model.assert_called_once_with('portable_dp',model_key='labse')
        assert app.session_state['alignment_results'][0][0]['run_id']=='test-run'
        assert any('Alignment complete' in item.value for item in app.success)
    st.cache_resource.clear()


def test_rejected_view_explains_legacy_scores_without_rerun():
    result={'run_id':'review-test','pair':{'pair_id':'demo'},'backend':'portable_dp','settings':{'semantic_floor':.72},
            'alignments':[{'fr':'Bonjour','en':'Hello','method':'portable_dp','status':'rejected','cosine':.5,'flags':[]}]}
    app=AppTest.from_file(str(APP))
    app.session_state['alignment_results']=[(result,'saved.json')]
    app.run()
    assert not app.exception
    assert app.selectbox(key='review-test-filter').value=='Rejected'
    assert any('0.500' in warning.value and '0.720' in warning.value for warning in app.warning)
    assert any(text.value=='Bonjour' for text in app.text)
