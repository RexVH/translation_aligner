import json
from pathlib import Path

import pytest

from translation_aligner.alignment import align, Settings, quality_flags
from translation_aligner.segments import Segment, parse_output
from translation_aligner.systran import SystranError


def segment(text, mt, i=0):
    return Segment(str(i), f'body.p{i}', text, mt)


def output(sentences):
    return {'outputs':[{'output':{'documents':[{'src_lang':'fr','tgt_lang':'en', 'trans_units':[
        {'id':'1','sentences':[{'id':f'Sp1.s{i}_o','source':{'text':text},'alt_transes':[{'target':{'text':mt}}]} for i,(text,mt) in enumerate(sentences)]}
    ]}]}}]}


def test_annotation_parsing_preserves_ids_and_checks_coverage():
    payload = output([('Bonjour.', 'Hello.'), (' Au revoir.', ' Goodbye.')])
    segments = parse_output(payload,'body.p3','Bonjour. Au revoir.','fr','en')
    assert segments[1].id == 'body.p3:1:Sp1.s1_o'
    assert segments[1].text == 'Au revoir.'
    with pytest.raises(SystranError,match='incomplete'):
        parse_output(payload,'body.p3','Bonjour. Au revoir. Missing text.','fr','en')


def test_anchor_intervals_do_not_join_across_exact_matches():
    fr = [segment('a','A',0),segment('b','B',1),segment('c','C',2)]
    en = [segment('xxx','yyy',0),segment('B','b',1),segment('zzz','www',2)]
    calls=[]
    def semantic(left,right,size):
        calls.append((left,right))
        return [([0],[0],.2,.9)]
    rows=align(fr,en,semantic)
    assert calls == [(['a'],['xxx']),(['c'],['zzz'])]
    assert [row['method'] for row in rows] == ['vecalign','exact','vecalign']


def test_grouping_and_omissions_preserve_every_segment():
    fr = [segment('bonjour','hi'),segment('monde','earth',1)]
    en = [segment('hello world','salut terre'),segment('extra','supplement',1)]
    rows=align(fr,en,lambda *args:[([0,1],[0],.1,.95),([],[1],.42,None)])
    assert rows[0]['fr']=='bonjour monde'
    assert rows[1]['status']=='unmatched'
    with pytest.raises(ValueError,match='coverage'):
        align(fr,en,lambda *args:[([0],[0],.1,.95)])


def test_quality_checks_reject_numeric_and_negation_defects():
    assert 'number_mismatch' in quality_flags('15 entrées','50 entries','50 entrées','15 entries')
    assert 'possible_negation_mismatch' in quality_flags('Ne pas archiver.','Archive.','Archiver.','Do not archive.')
    assert not quality_flags('1,5 mg','1.5 mg','1,5 mg','1.5 mg')


def test_low_semantic_score_is_not_accepted():
    rows=align([segment('abc','def')],[segment('xyz','uvw')],lambda *args:[([0],[0],.5,.5)])
    assert rows[0]['status']=='rejected'


def test_fuzzy_requires_both_directions():
    # English is very similar but the reverse translation is unrelated.
    fr=[segment('Vérifier toutes les pages du dossier.','Check all pages of the record.')]
    en=[segment('Check every page of the record.','Texte sans rapport.')]
    rows=align(fr,en,lambda *args:[([0],[0],.1,.9)])
    assert rows[0]['method']=='vecalign'
