"""Build review examples and a sampling plan without model calls."""
import copy
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/research'


def allocate(counts, size):
    """Largest remainder allocation with stable input-order tie breaking."""
    total = sum(counts)
    if size < 0 or total <= 0 or any(n < 0 for n in counts):
        raise ValueError('Invalid population or sample size')
    quotas = [n * size // total for n in counts]
    order = sorted(range(len(counts)), key=lambda i: (-(counts[i] * size % total), i))
    for i in order[:size - sum(quotas)]:
        quotas[i] += 1
    return quotas


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def build():
    seeds = json.loads((DATA / 'scenario-seeds.json').read_text())
    base, variants, labels = [], [], []
    for s in seeds:
        case = {
            'id': s['id'], 'family_id': s['id'], 'synthetic': True,
            'expert_reviewed': False, 'split': 'review_packet',
            'stratum': s['stratum'], 'age': s['age'], 'sex': s['sex'],
            'diagnosis': {'code': s['diagnosis_code'], 'text': s['diagnosis']},
            'review_at': '2026-10-06T12:00:00+03:00',
            'documents': [
                {'id': 'admission', 'kind': 'admission_note', 'event_at': '2026-10-01T10:00:00+03:00',
                 'available_at': '2026-10-01T11:00:00+03:00', 'text': s['complaints'] + ' ' + s['exam']},
                {'id': 'result', 'kind': 'result_or_consultation', 'event_at': '2026-10-02T10:00:00+03:00',
                 'available_at': '2026-10-03T10:00:00+03:00', 'text': s['result']},
                {'id': 'discharge', 'kind': 'discharge_draft', 'event_at': '2026-10-06T10:00:00+03:00',
                 'available_at': '2026-10-06T11:00:00+03:00', 'text': s['discharge'],
                 'diagnosis_code': s['diagnosis_code']},
            ],
            'claim_draft': {'principal_diagnosis_code': s['diagnosis_code'], 'synthetic': True,
                            'region': None, 'amount': None},
        }
        base.append(case)
        for mutation in ('late_result', 'code_mismatch'):
            v = copy.deepcopy(case)
            v['id'] = f"{case['id']}-{mutation}"
            if mutation == 'late_result':
                v['documents'][1]['available_at'] = '2026-10-07T10:00:00+03:00'
                reaction = 'result_not_available_at_review'
                refs = ['result']
            else:
                v['claim_draft']['principal_diagnosis_code'] = 'J18.9' if s['diagnosis_code'] != 'J18.9' else 'I50.9'
                reaction = 'request_coding_review'
                refs = ['discharge']
            variants.append(v)
            labels.append({'case_id': v['id'], 'family_id': s['id'], 'mutation': mutation,
                           'expected_engineering_reaction': reaction, 'document_ids': refs,
                           'clinical_ground_truth': False})
    write_json(DATA / 'base-cases.json', base)
    write_json(DATA / 'variants.json', variants)
    write_json(DATA / 'expectations.json', labels)
    with (ROOT / 'research/hospital-strata.csv').open() as f:
        strata = list(csv.DictReader(f))
    counts = [int(x['discharged_thousand_2024']) for x in strata]
    quotas = allocate(counts, 60)
    plan = {'source_id': 'STAT', 'population_year': 2024, 'total_discharged_thousand': 27515,
            'selected_discharged_thousand': sum(counts), 'planned_base_cases': 60,
            'generated_from_plan': 0, 'method': 'largest_remainder', 'strata': []}
    for row, count, quota in zip(strata, counts, quotas):
        plan['strata'].append({**row, 'discharged_thousand_2024': count,
                              'share_all_percent': round(count / 27515 * 100, 3),
                              'share_selected_percent': round(count / sum(counts) * 100, 3),
                              'planned_cases': quota, 'review_packet_examples': 2})
    write_json(ROOT / 'research/sampling-plan.json', plan)
    return base, variants, labels, plan


if __name__ == '__main__':
    base, variants, labels, plan = build()
    print(f'{len(base)} review examples; {len(variants)} variants; planned allocation: '
          f'{[s["planned_cases"] for s in plan["strata"]]}')
