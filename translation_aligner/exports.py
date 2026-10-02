"""Auditable per-pair resources and immutable aggregate snapshots."""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
from uuid import uuid4
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

from filelock import FileLock

from .alignment import normalize

EXPORT_VERSION = 1
# Seed terminology: match only when BOTH terms occur in an accepted aligned pair.
# No generated translation is inserted into the dictionary.
TERMS = {
    'dossier de fabrication': ['manufacturing record', 'batch manufacturing record', 'batch record'],
    'certificat d’analyse': ['certificate of analysis'],
    'numéro de lot': ['batch number', 'lot number'],
    'assurance qualité': ['quality assurance'],
    'contrôle qualité': ['quality control'],
    'traçabilité': ['traceability'],
    'matière première': ['raw material'],
    'produit fini': ['finished product'],
    'principe actif': ['active ingredient', 'active pharmaceutical ingredient'],
    'conditionnement primaire': ['primary packaging'],
}
GENERIC = {'objet','purpose','scope','champ d’application','champ d\'application','terminologie','terminology',
           'code','terme','term','contrôles préliminaires','initial checks','traitement des écarts','handling discrepancies'}


def sentence(text):
    return bool(re.search(r'[.!?](?:["»”])?\s*$', text)) and len(re.findall(r'\w+', text)) >= 3


def short_phrase(text):
    words = re.findall(r"[^\W\d_]+", text, re.UNICODE)
    return (1 <= len(words) <= 8 and not re.search(r'[.!?;:\d#]', text)
            and normalize(text) not in {normalize(x) for x in GENERIC}
            and not re.match(r'(?i)^(?:vérifier|enregistrer|joindre|identifier|informer|ne |check |record |attach |identify |notify |do )', text))


def find_term(text, term):
    # Preserve the actual original/expert substring, not the seed spelling.
    pattern = ''.join("['’]" if char in "'’" else re.escape(char) for char in term)
    match = re.search(r'(?<!\w)' + pattern + r'(?!\w)', text, re.IGNORECASE)
    return match.group(0) if match else None


def candidates(result):
    entries, excluded = [], []
    for index, row in enumerate(result['alignments']):
        count_before=len(entries)
        fr,en = row.get('fr','').strip(),row.get('en','').strip()
        if row.get('status') != 'aligned' or row.get('flags') or not fr or not en:
            excluded.append({'alignment':index,'reason':'Rejected, unmatched, flagged, or empty alignment'})
            continue
        provenance = dict(run_id=result['run_id'],pair_id=result['pair']['pair_id'],alignment=index,
                          fr_ids=row.get('fr_ids',[]),en_ids=row.get('en_ids',[]))
        def add(kind, source, target, evidence):
            if kind == 'dictionary' and ('#' in source or '#' in target):
                excluded.append({'alignment':index,'reason':'Dictionary term contains unsupported # character'})
                return
            entries.append(dict(kind=kind,fr=source,en=target,evidence=evidence,provenance=provenance))
        if sentence(fr) and sentence(en):
            add('tm',fr,en,'accepted sentence alignment')
        if short_phrase(fr) and short_phrase(en):
            add('dictionary',fr,en,'accepted short expression; heuristic, not a pharma classifier')
        for source, targets in TERMS.items():
            found_source = find_term(fr,source)
            if found_source:
                # Longest matching target avoids nested duplicates like "batch record".
                for target in sorted(targets,key=len,reverse=True):
                    found_target=find_term(en,target)
                    if found_target:
                        add('dictionary',found_source,found_target,'seed term observed in original and expert text')
                        break
        if len(entries)==count_before:
            excluded.append({'alignment':index,'reason':'Accepted alignment does not qualify as a sentence or terminology entry'})
    return entries, excluded


def consolidate(entries):
    groups=defaultdict(lambda: defaultdict(list))
    for entry in entries:
        groups[(entry['kind'],normalize(entry['fr']))][normalize(entry['en'])].append(entry)
    accepted,conflicts=[],[]
    for (kind,source),targets in sorted(groups.items()):
        variants=[]
        for _, occurrences in sorted(targets.items()):
            variants.append(dict(fr=occurrences[0]['fr'],en=occurrences[0]['en'],
                                 provenance=[item['provenance'] for item in occurrences],
                                 evidence=sorted({item['evidence'] for item in occurrences})))
        if len(variants)>1:
            fingerprint=hashlib.sha256(json.dumps([kind,source,sorted(targets)],ensure_ascii=False).encode()).hexdigest()
            conflicts.append(dict(kind=kind,source_key=source,candidate_fingerprint=fingerprint,variants=variants,
                                  action='Excluded pending expert resolution'))
        else:
            accepted.append(dict(kind=kind,**variants[0]))
    return accepted,conflicts


def tmx(entries):
    root=ET.Element('tmx',version='1.4')
    ET.SubElement(root,'header',creationtool='translation_aligner',creationtoolversion=str(EXPORT_VERSION),
                  segtype='sentence',o_tmf='translation_aligner',adminlang='en',srclang='fr',datatype='plaintext')
    body=ET.SubElement(root,'body')
    for index,entry in enumerate(entries):
        if entry['kind']!='tm':
            continue
        unit=ET.SubElement(body,'tu',tuid=str(index+1))
        for lang in ('fr','en'):
            variant=ET.SubElement(unit,'tuv',{'{http://www.w3.org/XML/1998/namespace}lang':lang})
            ET.SubElement(variant,'seg').text=entry[lang]
    ET.indent(root)
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)


def dictionary(entries):
    def escape(text):
        text=' '.join(text.split())
        return text.replace('\\','\\\\\\\\').replace('"','\\"').replace('(','\\(').replace(')','\\)')
    lines=['#ENCODING=UTF-8','#SUMMARY=Aligned FR EN terminology','#MULTI','#FR\tEN']
    lines.extend(escape(entry['fr'])+'\t'+escape(entry['en']) for entry in entries if entry['kind']=='dictionary')
    return ('\n'.join(lines)+'\n').encode('utf-8')


def json_write(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def write_resources(folder, entries, excluded):
    folder.mkdir(parents=True,exist_ok=True)
    accepted,conflicts=consolidate(entries)
    (folder/'translation_memory.tmx').write_bytes(tmx(accepted))
    (folder/'dictionary.txt').write_bytes(dictionary(accepted))
    json_write(folder/'entries.json',accepted)
    json_write(folder/'conflicts.json',conflicts)
    json_write(folder/'excluded.json',excluded)
    return {'tm_entries':sum(e['kind']=='tm' for e in accepted),
            'dictionary_entries':sum(e['kind']=='dictionary' for e in accepted),
            'conflicts':len(conflicts),'excluded_alignments':len(excluded)}


def export_run(result, root=Path('local_data/resources')):
    """Replace this pair's contribution and atomically publish a new master.

    Old versions are immutable. The lock serializes publishers; latest.json is
    replaced only after all files are complete. A failed write leaves no new
    published pointer. Repeating the active run is idempotent.
    """
    root=Path(root)
    root.mkdir(parents=True,exist_ok=True)
    with FileLock(str(root/'publish.lock'),timeout=30):
        pointer=root/'latest.json'
        previous=json.loads(pointer.read_text(encoding='utf-8')) if pointer.exists() else None
        active=dict(previous['active_pairs']) if previous else {}
        pair_key=result['pair']['pair_id'].casefold()
        content_hash=hashlib.sha256(json.dumps({k:v for k,v in result.items() if k!='resource_export'},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        contribution_id=hashlib.sha256(f'{EXPORT_VERSION}:{content_hash}'.encode()).hexdigest()
        if active.get(pair_key)==contribution_id:
            return dict(previous,pair_folder=str(root/'pairs'/contribution_id),master_folder=str(root/'masters'/previous['version']))
        pair_folder=root/'pairs'/contribution_id
        entries,excluded=candidates(result)
        if not pair_folder.exists():
            staging=root/('pending-pair-'+uuid4().hex)
            counts=write_resources(staging,entries,excluded)
            json_write(staging/'candidates.json',entries)
            json_write(staging/'manifest.json',dict(run_id=result['run_id'],pair=result['pair'],input_hashes=result.get('input_hashes'),
                                                  model=result.get('model'),model_revision=result.get('model_revision'),
                                                  settings=result.get('settings'),exporter_version=EXPORT_VERSION,counts=counts))
            pair_folder.parent.mkdir(exist_ok=True)
            staging.rename(pair_folder)
        active[pair_key]=contribution_id
        all_entries=[]
        for identifier in active.values():
            all_entries.extend(json.loads((root/'pairs'/identifier/'candidates.json').read_text(encoding='utf-8')))
        version=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]
        staging=root/('pending-master-'+uuid4().hex)
        counts=write_resources(staging,all_entries,[])
        before=json.loads((root/'masters'/previous['version']/'entries.json').read_text(encoding='utf-8')) if previous else []
        after=json.loads((staging/'entries.json').read_text(encoding='utf-8'))
        identities=lambda rows: {(e['kind'],normalize(e['fr']),normalize(e['en'])) for e in rows}
        manifest=dict(version=version,parent=previous['version'] if previous else None,active_pairs=active,
                      contributing_run=result['run_id'],exporter_version=EXPORT_VERSION,counts=counts,
                      added=sorted(identities(after)-identities(before)),removed=sorted(identities(before)-identities(after)))
        json_write(staging/'manifest.json',manifest)
        destination=root/'masters'/version
        destination.parent.mkdir(exist_ok=True)
        staging.rename(destination)
        temporary=root/('latest-'+uuid4().hex+'.tmp')
        json_write(temporary,manifest)
        temporary.replace(pointer)
        return dict(manifest,pair_folder=str(pair_folder),master_folder=str(destination))


def resource_bundle(export):
    output=io.BytesIO()
    with ZipFile(output,'w',ZIP_DEFLATED) as archive:
        for label,key in [('pair','pair_folder'),('master','master_folder')]:
            for path in sorted(Path(export[key]).iterdir()):
                if path.is_file():
                    archive.write(path,f'{label}/{path.name}')
    return output.getvalue()
