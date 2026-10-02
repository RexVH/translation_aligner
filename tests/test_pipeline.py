import json
from pathlib import Path
from unittest.mock import patch

from translation_aligner.intake import Pair
from translation_aligner.pipeline import run_pair
from translation_aligner.segments import Segment


def test_completed_pair_saves_auditable_result_and_correct_backend(tmp_path):
    class Backend:
        backend = 'portable_dp'
        model_id = 'test-model'
        model_revision = 'test-revision'
        def __call__(self,*args):
            return [([0],[0],.1,.9)]
    def translations(blocks,source,*args):
        return ([Segment('api:1','body.p1','Bonjour monde.' if source=='fr' else 'Hello world.',
                         'Greetings earth.' if source=='fr' else 'Salut terre.')],['cache-key'])
    samples = Path(__file__).parents[1]/'samples'
    with patch('translation_aligner.pipeline.translate_blocks',side_effect=translations):
        result,path=run_pair(Pair('demo','demo.docx','demo-EN.docx'),
                             (samples/'SOP_DEMO_001.docx').read_bytes(),(samples/'SOP_DEMO_001-EN.docx').read_bytes(),
                             'private-key','https://api.test',Backend(),root=tmp_path)
    saved=json.loads(path.read_text(encoding='utf-8'))
    assert saved['alignments'][0]['method']=='portable_dp'
    assert 'vecalign_cost' not in saved['alignments'][0]
    assert saved['segments']['fr'][0]['id']=='api:1'
    assert saved['model']=='test-model' and saved['model_revision']=='test-revision'
    assert len(saved['input_hashes'][0])==64
    assert 'private-key' not in path.read_text(encoding='utf-8')
