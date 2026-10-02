from unittest.mock import patch

import numpy as np

from translation_aligner.models import MODELS
from translation_aligner.semantic import SemanticAligner


def test_model_loading_and_embedding_cache_are_isolated(tmp_path):
    class Model:
        def __init__(self,name,**kwargs):
            self.name=name
            self.dimension=3 if 'MiniLM' in name else 5
        def encode(self,texts,**kwargs):
            return np.ones((len(texts),self.dimension),dtype=np.float32)
    with patch('sentence_transformers.SentenceTransformer',side_effect=Model) as load:
        a=SemanticAligner('portable_dp',tmp_path,model_key='minilm')
        b=SemanticAligner('portable_dp',tmp_path,model_key='labse')
        assert a.encode(['same text']).shape==(1,3)
        assert b.encode(['same text']).shape==(1,5)
        assert len(list(tmp_path.glob('*.npy')))==2
        assert load.call_args.kwargs['revision']==MODELS['labse']['revision']
        assert b.model_id==MODELS['labse']['id']
