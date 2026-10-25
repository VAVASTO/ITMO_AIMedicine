import csv
from datetime import datetime
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('research_builder', ROOT / 'scripts/build_research_data.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def read(path):
    return json.loads((ROOT / path).read_text())


def test_sampling_plan_matches_published_counts_and_integer_budget():
    plan = read('research/sampling-plan.json')
    counts = [4928, 2805, 2525, 636, 2357, 164]
    assert [r['discharged_thousand_2024'] for r in plan['strata']] == counts
    assert plan['selected_discharged_thousand'] == 13415
    assert plan['total_discharged_thousand'] == 27515
    assert [r['planned_cases'] for r in plan['strata']] == [22, 13, 11, 3, 10, 1]
    assert sum(r['planned_cases'] for r in plan['strata']) == plan['planned_base_cases'] == 60
    assert plan['generated_from_plan'] == 0
    assert builder.allocate([1, 1, 1], 2) == [1, 1, 0]


def test_scenarios_are_review_examples_with_sources_and_no_claim_of_validation():
    cases = read('data/research/base-cases.json')
    seeds = read('data/research/scenario-seeds.json')
    sources = {s['id'] for s in read('research/sources.json')}
    assert len(cases) == len({c['id'] for c in cases}) == 12
    assert len({c['stratum'] for c in cases}) == 6
    assert len({c['documents'][0]['text'] for c in cases}) == 12
    assert all(s['reference_id'] in sources for s in seeds)
    for c in cases:
        assert c['synthetic'] and not c['expert_reviewed']
        assert c['split'] == 'review_packet'
        assert c['claim_draft']['amount'] is None
        assert len({d['id'] for d in c['documents']}) == len(c['documents'])
        for d in c['documents']:
            assert datetime.fromisoformat(d['event_at']) <= datetime.fromisoformat(d['available_at'])
            assert datetime.fromisoformat(d['available_at']) <= datetime.fromisoformat(c['review_at'])


def test_expected_reactions_are_separate_from_model_inputs_and_traceable():
    cases = read('data/research/variants.json')
    expected = read('data/research/expectations.json')
    assert len(cases) == len(expected) == 24
    by_id = {c['id']: c for c in cases}
    for e in expected:
        c = by_id[e['case_id']]
        assert c['family_id'] == e['family_id']
        assert 'expected_engineering_reaction' not in json.dumps(c)
        assert 'mutation' not in c
        assert not e['clinical_ground_truth']
        assert set(e['document_ids']) <= {d['id'] for d in c['documents']}


def test_time_mutations_do_not_let_future_documents_become_current_evidence():
    variants = read('data/research/variants.json')
    labels = {e['case_id']: e for e in read('data/research/expectations.json')}
    for c in variants:
        if labels[c['id']]['mutation'] != 'late_result':
            continue
        available = [d['id'] for d in c['documents'] if datetime.fromisoformat(d['available_at']) <= datetime.fromisoformat(c['review_at'])]
        assert 'result' not in available
        assert 'admission' in available and 'discharge' in available


def test_code_variants_preserve_original_record_and_only_raise_review_question():
    base = {c['id']: c for c in read('data/research/base-cases.json')}
    labels = {e['case_id']: e for e in read('data/research/expectations.json')}
    for c in read('data/research/variants.json'):
        if labels[c['id']]['mutation'] != 'code_mismatch':
            continue
        original = base[c['family_id']]
        assert c['documents'] == original['documents']
        assert c['diagnosis'] == original['diagnosis']
        assert c['claim_draft']['principal_diagnosis_code'] != c['diagnosis']['code']
        assert labels[c['id']]['expected_engineering_reaction'] == 'request_coding_review'


def test_competitor_evidence_references_exist_and_identifiers_are_unique():
    sources = read('research/sources.json')
    ids = {s['id'] for s in sources}
    assert len(ids) == len(sources)
    comparisons = read('research/competitors.json')
    assert len(comparisons) == 12
    assert all(set(c['sources']) <= ids for c in comparisons)
    assert all(s['url'].startswith('https://') for s in sources)
