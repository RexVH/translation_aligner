"""Reviewed multilingual sentence models; pinned for repeatable experiments."""
MODELS = {
    'minilm': dict(id='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',
                   revision='e8f8c211226b894fcb81acc59f3b34ba3efd5f42',
                   label='Multilingual MiniLM — compact default',
                   description='Compact multilingual sentence model; start here for CPU experiments.'),
    'mpnet': dict(id='sentence-transformers/paraphrase-multilingual-mpnet-base-v2',
                  revision='4328cf26390c98c5e3c738b4460a05b95f4911f5',
                  label='Multilingual MPNet — larger paraphrase model',
                  description='Larger multilingual paraphrase model. Expect more RAM and longer CPU runs.'),
    'labse': dict(id='sentence-transformers/LaBSE',
                  revision='836121a0533e5664b21c7aacc5d22951f2b8b25b',
                  label='LaBSE — cross-language sentence matching',
                  description='Language-agnostic sentence model for cross-language matching; larger download and CPU footprint.'),
    'distiluse': dict(id='sentence-transformers/distiluse-base-multilingual-cased-v2',
                      revision='bfe45d0732ca50787611c0fe107ba278c7f3f889',
                      label='Multilingual DistilUSE — alternative baseline',
                      description='Another multilingual sentence model for comparing alignment behavior.'),
}
