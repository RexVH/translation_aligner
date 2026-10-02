from copy import deepcopy
import json
from xml.etree import ElementTree as ET

from translation_aligner.exports import candidates, consolidate, export_run, resource_bundle
from translation_aligner.review import rejection_reasons


def run(pair, text='Check the record.', run_id='r1'):
    return dict(pair={'pair_id':pair},run_id=run_id,alignments=[
        dict(fr='Vérifier le dossier.',en=text,status='aligned',flags=[]),
        dict(fr='certificat d’analyse',en='certificate of analysis',status='aligned',flags=[]),
        dict(fr='T01',en='T01',status='aligned',flags=[]),
        dict(fr='15 entrées.',en='50 entries.',status='rejected',flags=['number_mismatch']),
    ])


def test_resource_classification_and_valid_tmx(tmp_path):
    result=export_run(run('a'),tmp_path)
    from pathlib import Path
    folder=Path(result['pair_folder'])
    xml=ET.parse(folder/'translation_memory.tmx')
    assert xml.getroot().attrib['version']=='1.4'
    assert [s.text for s in xml.findall('.//seg')]==['Vérifier le dossier.','Check the record.']
    assert 'certificat d’analyse\tcertificate of analysis' in (folder/'dictionary.txt').read_text(encoding='utf-8')
    assert 'T01' not in (folder/'dictionary.txt').read_text(encoding='utf-8')
    assert result['counts']['dictionary_entries']==1
    assert len(resource_bundle(result))>0


def test_conflict_removes_previously_accepted_entry_and_preserves_snapshot(tmp_path):
    first=export_run(run('a'),tmp_path)
    second=export_run(run('b','Review the file.','r2'),tmp_path)
    assert first['counts']['tm_entries']==1
    assert second['counts']['tm_entries']==0
    assert second['counts']['conflicts']==1
    assert second['parent']==first['version']
    assert second['removed']
    assert 'Check the record.' in (tmp_path/'masters'/first['version']/'translation_memory.tmx').read_text(encoding='utf-8')
    conflict=json.loads((tmp_path/'masters'/second['version']/'conflicts.json').read_text(encoding='utf-8'))[0]
    assert len(conflict['variants'])==2


def test_reprocessing_replaces_contribution_and_repeat_is_idempotent(tmp_path):
    a=run('a')
    first=export_run(a,tmp_path)
    assert export_run(a,tmp_path)['version']==first['version']
    a['resource_export']=first
    assert export_run(a,tmp_path)['version']==first['version']
    second=export_run(run('a','Review the file.','r2'),tmp_path)
    assert len(second['active_pairs'])==1
    assert second['counts']['conflicts']==0
    assert len(second['added'])==1 and len(second['removed'])==1


def test_identical_entries_collapse_with_provenance(tmp_path):
    export_run(run('a'),tmp_path)
    second=export_run(run('b',run_id='r2'),tmp_path)
    entries=json.loads((tmp_path/'masters'/second['version']/'entries.json').read_text(encoding='utf-8'))
    tm=next(e for e in entries if e['kind']=='tm')
    assert len(tm['provenance'])==2


def test_terms_can_come_from_sentences_and_xml_is_escaped(tmp_path):
    result=run('a')
    result['alignments']=[dict(fr='Joindre le certificat d’analyse <A>.',en='Attach the certificate of analysis <A>.',status='aligned',flags=[])]
    entries,_=candidates(result)
    assert {e['kind'] for e in entries}=={'tm','dictionary'}
    exported=export_run(result,tmp_path)
    parsed=ET.parse(tmp_path/'masters'/exported['version']/'translation_memory.tmx')
    assert parsed.find('.//seg').text.endswith('<A>.')


def test_legacy_rejection_reason_infers_score_threshold():
    row=dict(status='rejected',cosine=.55,flags=[])
    assert rejection_reasons(row,{'semantic_floor':.72})==['Semantic similarity 0.550 is below the required 0.720.']
    row.update(flags=['number_mismatch'],fr='15 entrées',en='50 entries')
    reasons=rejection_reasons(row,{'semantic_floor':.72})
    assert len(reasons)==2 and 'FR [15]; EN [50]' in reasons[0]
