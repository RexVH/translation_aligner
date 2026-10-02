"""CPU embeddings with separate VecAlign and portable exact-DP backends."""
import ast
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
from .models import MODELS

MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
MODEL_REVISION = 'e8f8c211226b894fcb81acc59f3b34ba3efd5f42'


class SemanticAligner:
    def __init__(self, backend='vecalign', cache=Path('local_data/embeddings'), model_key='minilm'):
        if model_key not in MODELS:
            raise ValueError('Unknown embedding model.')
        self.model_id = MODELS[model_key]['id']
        self.model_revision = MODELS[model_key]['revision']
        if backend not in ('vecalign', 'portable_dp'):
            raise ValueError('Unknown semantic backend.')
        if backend == 'vecalign' and importlib.util.find_spec('vecalign') is None:
            raise RuntimeError('VecAlign is not installed. Install requirements-vecalign.txt after installing Microsoft C++ Build Tools, or select Portable semantic DP.')
        from sentence_transformers import SentenceTransformer
        import torch
        torch.set_num_threads(min(4, os.cpu_count() or 1))
        self.backend = backend
        model_options = dict(device='cpu', cache_folder='local_data/models', revision=self.model_revision)
        try:
            self.model = SentenceTransformer(self.model_id, local_files_only=True, **model_options)
        except OSError:
            self.model = SentenceTransformer(self.model_id, **model_options)
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.memory = {}

    def encode(self, texts):
        missing = list(dict.fromkeys(text for text in texts if text not in self.memory))
        compute = []
        for text in missing:
            key = hashlib.sha256((self.model_id + self.model_revision + '\0' + text).encode()).hexdigest()
            path = self.cache / (key + '.npy')
            if path.exists():
                self.memory[text] = np.load(path, allow_pickle=False)
            else:
                compute.append((text, path))
        if compute:
            vectors = self.model.encode([text for text, _ in compute], batch_size=16, normalize_embeddings=True, show_progress_bar=False)
            for (text, path), vector in zip(compute, vectors):
                self.memory[text] = vector.astype(np.float32)
                np.save(path, self.memory[text], allow_pickle=False)
        return np.asarray([self.memory[text] for text in texts], dtype=np.float32)

    def __call__(self, source, target, max_group):
        if self.backend == 'vecalign':
            return self.vecalign(source, target, max_group)
        return self.portable(source, target, max_group)

    def groups(self, lines, maximum):
        return {(i, size): ' '.join(lines[i:i+size]) for i in range(len(lines)) for size in range(1, min(maximum, len(lines)-i)+1)}

    def portable(self, source, target, maximum):
        """Global monotone dynamic programming, explicitly not VecAlign."""
        left, right = self.groups(source, maximum-1), self.groups(target, maximum-1)
        lv = dict(zip(left, self.encode(list(left.values()))))
        rv = dict(zip(right, self.encode(list(right.values()))))
        n, m = len(source), len(target)
        costs = np.full((n+1,m+1), np.inf)
        costs[0,0] = 0
        back = {}
        for i in range(n+1):
            for j in range(m+1):
                moves = [(1,0,0.42,None), (0,1,0.42,None)]
                for a in range(1, min(maximum-1,n-i)+1):
                    for b in range(1,min(maximum-a,m-j)+1):
                        cosine = float(np.dot(lv[i,a],rv[j,b]))
                        moves.append((a,b,1-cosine+0.08*(a+b-2),cosine))
                for a,b,cost,cosine in moves:
                    if i+a<=n and j+b<=m and costs[i,j]+cost < costs[i+a,j+b]:
                        costs[i+a,j+b] = costs[i,j]+cost
                        back[i+a,j+b] = (i,j,cost,cosine)
        result = []
        i,j = n,m
        while i or j:
            pi,pj,cost,cosine = back[i,j]
            result.append((list(range(pi,i)),list(range(pj,j)),cost,cosine))
            i,j = pi,pj
        return result[::-1]

    def vecalign(self, source, target, maximum):
        with tempfile.TemporaryDirectory(prefix='vecalign-') as directory:
            folder = Path(directory)
            for name, lines in (('src',source),('tgt',target)):
                (folder/name).write_text('\n'.join(lines)+'\n',encoding='utf-8')
                overlaps = list(dict.fromkeys(self.groups(lines, maximum).values()))
                (folder/(name+'.overlaps')).write_text('\n'.join(overlaps)+'\n',encoding='utf-8')
                self.encode(overlaps).tofile(folder/(name+'.emb'))
            command = [sys.executable,'-m','vecalign.vecalign','--src',str(folder/'src'),'--tgt',str(folder/'tgt'),
                       '--src_embed',str(folder/'src.overlaps'),str(folder/'src.emb'),
                       '--tgt_embed',str(folder/'tgt.overlaps'),str(folder/'tgt.emb'), '--alignment_max_size',str(maximum)]
            completed = subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=300,
                                       creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if completed.returncode:
                raise RuntimeError('VecAlign failed; no substitute results were generated. Check the VecAlign installation.')
            result = []
            for line in completed.stdout.splitlines():
                if not line.startswith('['):
                    continue
                left,right,cost = line.split(':')
                ii,jj = ast.literal_eval(left),ast.literal_eval(right)
                cosine = None
                if ii and jj:
                    vectors = self.encode([' '.join(source[i] for i in ii),' '.join(target[j] for j in jj)])
                    cosine = float(np.dot(*vectors))
                result.append((ii,jj,float(cost),cosine))
            return result
