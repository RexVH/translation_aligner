"""Explain decisions in current and older saved alignment runs."""
import re

METHODS = {'exact':'Exact match','fuzzy':'Bidirectional fuzzy match','vecalign':'VecAlign',
           'portable_dp':'Portable semantic DP','unmatched':'No counterpart'}


def rejection_reasons(row, settings):
    reasons = []
    flags = row.get('flags', [])
    if 'number_mismatch' in flags:
        numbers = lambda t: ', '.join(re.findall(r'\d+(?:[.,]\d+)?',t)) or 'none'
        reasons.append(f"Numbers differ: FR [{numbers(row.get('fr',''))}]; EN [{numbers(row.get('en',''))}].")
    if 'possible_negation_mismatch' in flags:
        reasons.append('Possible negation mismatch: a negative instruction differs in one of the original/MT comparisons. Check the wording below.')
    cosine = row.get('cosine')
    threshold = row.get('semantic_threshold', settings.get('semantic_floor', .72))
    if cosine is not None and cosine < threshold:
        reasons.append(f'Semantic similarity {cosine:.3f} is below the required {threshold:.3f}.')
    for flag in flags:
        if flag not in ('number_mismatch','possible_negation_mismatch','low_semantic_similarity'):
            reasons.append(flag.replace('_',' ').capitalize())
    if row.get('status') == 'unmatched':
        reasons.append('No English counterpart selected.' if row.get('fr') else 'No French counterpart selected.')
    if row.get('status') == 'rejected' and not reasons:
        reasons.append('Rejected by this saved run; no detailed reason was recorded.')
    return reasons
