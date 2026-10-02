"""Order-preserving exact/fuzzy anchors followed by real VecAlign intervals."""
from dataclasses import dataclass, asdict
import re
import unicodedata

from rapidfuzz.fuzz import ratio


@dataclass(frozen=True)
class Settings:
    fuzzy_floor: float = 80.0
    fuzzy_score: float = 88.0
    ambiguity_margin: float = 4.0
    semantic_floor: float = 0.72
    max_group: int = 4


def normalize(text):
    return ' '.join(unicodedata.normalize('NFC', text).replace('’', "'").split()).casefold()


def scores(fr, en):
    a = ratio(normalize(fr.text), normalize(en.mt))
    b = ratio(normalize(fr.mt), normalize(en.text))
    return a, b, 0.75 * min(a, b) + 0.25 * max(a, b)


def quality_flags(fr, en, mt_fr, mt_en):
    def numbers(text):
        return sorted(x.replace(',', '.') for x in re.findall(r'\d+(?:[.,]\d+)?', text))
    flags = []
    if numbers(fr) != numbers(en):
        flags.append('number_mismatch')
    # Conservative heuristic, not linguistic proof; blocks automatic acceptance.
    def negative(text, language):
        expression = r"\b(?:not|never|no|without|cannot)\b|n't\b" if language == 'en' else r"\b(?:pas|jamais|sans|aucun|aucune|ni)\b"
        return bool(re.search(expression, normalize(text)))
    if negative(fr, 'fr') != negative(mt_fr, 'fr') or negative(en, 'en') != negative(mt_en, 'en'):
        flags.append('possible_negation_mismatch')
    return flags


def intervals(anchors, n, m):
    previous_i = previous_j = -1
    for i, j, *_ in anchors + [(n, m, '', 0, 0, 0)]:
        yield list(range(previous_i + 1, i)), list(range(previous_j + 1, j))
        previous_i, previous_j = i, j


def monotonic(candidates):
    """Maximum-weight noncrossing chain; each segment used at most once."""
    candidates = sorted(candidates)
    best, previous = [], []
    for k, (i, j, *_) in enumerate(candidates):
        choices = [(best[h], h) for h in range(k) if candidates[h][0] < i and candidates[h][1] < j]
        value, parent = max(choices, default=(0, -1))
        best.append(value + candidates[k][-1])
        previous.append(parent)
    chain = []
    k = max(range(len(best)), key=best.__getitem__) if best else -1
    while k >= 0:
        chain.append(candidates[k])
        k = previous[k]
    return chain[::-1]


def align(fr, en, semantic, settings=Settings(), progress=lambda *args: None):
    exact = []
    for i, left in enumerate(fr):
        for j, right in enumerate(en):
            a, b, score = scores(left, right)
            if max(a, b) == 100 and not quality_flags(left.text, right.text, right.mt, left.mt):
                exact.append((i, j, 'exact', a, b, score))
    # Repeated exact candidates need context: only unambiguous anchors lock now.
    exact = [x for x in exact if sum(y[0] == x[0] for y in exact) == 1 and sum(y[1] == x[1] for y in exact) == 1]
    anchors = monotonic(exact)
    fuzzy = []
    for ii, jj in intervals(anchors, len(fr), len(en)):
        pool = []
        for i in ii:
            for j in jj:
                a, b, score = scores(fr[i], en[j])
                if min(a, b) >= settings.fuzzy_floor and score >= settings.fuzzy_score and not quality_flags(fr[i].text, en[j].text, en[j].mt, fr[i].mt):
                    pool.append((i, j, 'fuzzy', a, b, score))
        for candidate in pool:
            competitors = [x[-1] for x in pool if x != candidate and (x[0] == candidate[0] or x[1] == candidate[1])]
            if not competitors or candidate[-1] - max(competitors) >= settings.ambiguity_margin:
                fuzzy.append(candidate)
    anchors = sorted(anchors + monotonic(fuzzy))
    rows = []

    def add(ii, jj, method, cost=None, similarity=None):
        left = ' '.join(fr[i].text for i in ii)
        right = ' '.join(en[j].text for j in jj)
        forward = ' '.join(fr[i].mt for i in ii)
        reverse = ' '.join(en[j].mt for j in jj)
        flags = quality_flags(left, right, reverse, forward) if ii and jj else []
        status = 'aligned' if ii and jj else 'unmatched'
        if flags or (similarity is not None and similarity < settings.semantic_floor):
            status = 'rejected'
        if similarity is not None and similarity < settings.semantic_floor:
            flags.append('low_semantic_similarity')
        a, b = (ratio(normalize(left), normalize(reverse)), ratio(normalize(forward), normalize(right))) if ii and jj else (None, None)
        rows.append(dict(fr_indices=ii, en_indices=jj, fr_ids=[fr[i].id for i in ii], en_ids=[en[j].id for j in jj],
                         fr=left, en=right, mt_en=forward, mt_fr=reverse, method=method, status=status,
                         fr_score=a, en_score=b, conservative_score=0.75 * min(a,b) + 0.25 * max(a,b) if a is not None else None,
                         cosine=similarity, semantic_threshold=settings.semantic_floor, vecalign_cost=cost, flags=flags))

    for i, j, method, *_ in anchors:
        add([i], [j], method)
    gaps = list(intervals(anchors, len(fr), len(en)))
    semantic_method = getattr(semantic, 'backend', 'vecalign')
    for k, (ii, jj) in enumerate(gaps):
        progress(k / max(1, len(gaps)), f"Semantic alignment: interval {k + 1}/{len(gaps)}")
        if ii and jj:
            for si, tj, cost, cosine in semantic([fr[i].text for i in ii], [en[j].text for j in jj], settings.max_group):
                add([ii[i] for i in si], [jj[j] for j in tj], semantic_method, cost, cosine)
        else:
            for i in ii:
                add([i], [], 'unmatched')
            for j in jj:
                add([], [j], 'unmatched')
    # No semantic backend may drop or duplicate indices without detection.
    if sorted(i for row in rows for i in row['fr_indices']) != list(range(len(fr))) or sorted(j for row in rows for j in row['en_indices']) != list(range(len(en))):
        raise ValueError('Alignment coverage validation failed.')
    for row in rows:
        if row['method'] == 'portable_dp':
            row['semantic_cost'] = row.pop('vecalign_cost')
    return sorted(rows, key=lambda r: (r['fr_indices'][0] / max(1,len(fr)) if r['fr_indices'] else r['en_indices'][0] / max(1,len(en)), r['en_indices']))
