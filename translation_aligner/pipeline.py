"""Durable per-pair alignment artifacts; no dictionary/TM publication yet."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from .alignment import Settings, align
from .intake import extract_body
from .segments import translate_blocks
from .semantic import MODEL, MODEL_REVISION
from .exports import export_run


def run_pair(pair, source_bytes, target_bytes, key, endpoint, semantic, settings=Settings(),
             progress=lambda *args: None, root=Path('local_data'), profiles=(None,None)):
    root = Path(root)
    fr_blocks,en_blocks = extract_body(source_bytes),extract_body(target_bytes)
    if not fr_blocks or not en_blocks:
        raise ValueError('Both documents must contain main-body text.')
    fr,fr_cache = translate_blocks(fr_blocks,'fr','en',key,endpoint,root/'translations',
                                   lambda p,t: progress(p*.4,t), profiles[0])
    en,en_cache = translate_blocks(en_blocks,'en','fr',key,endpoint,root/'translations',
                                   lambda p,t: progress(.4+p*.4,t), profiles[1])
    rows = align(fr,en,semantic,settings,lambda p,t: progress(.8+p*.19,t))
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]
    result = dict(schema_version=1,run_id=run_id,pair=asdict(pair),settings=asdict(settings),
                  model=semantic.model_id,model_revision=semantic.model_revision,backend=semantic.backend,endpoint=endpoint,profiles=profiles,
                  input_hashes=[hashlib.sha256(data).hexdigest() for data in (source_bytes,target_bytes)],
                  response_cache_keys={'fr':fr_cache,'en':en_cache},
                  segments={'fr':[asdict(s) for s in fr],'en':[asdict(s) for s in en]}, alignments=rows)
    directory = root/'runs'/run_id
    directory.mkdir(parents=True)
    temporary = directory/'alignment.tmp'
    temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(directory/'alignment.json')
    progress(.99,'Generating dictionary, TM and master snapshot')
    result['resource_export']=export_run(result,root/'resources')
    temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(directory/'alignment.json')
    progress(1,'Alignment and resources saved')
    return result, directory/'alignment.json'
