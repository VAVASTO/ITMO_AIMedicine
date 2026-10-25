"""Check specification data integrity without claiming to test the future feature."""
from datetime import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT / path).read_text())


def test_new_variants_do_not_inflate_independent_families_or_leak_labels():
    cases = read('data/research/feature-cases.json')
    expected = read('data/research/feature-expectations.json')
    assert len(cases) == len({c['id'] for c in cases}) == 14
    assert {c['family_id'] for c in cases} == {'research-03'}
    assert {e['case_id'] for e in expected} == {c['id'] for c in cases}
    for c in cases:
        assert c['synthetic'] and not c['expert_reviewed']
        assert c['split'] == 'development_specification'
        assert 'expected_status' not in json.dumps(c)
        assert 'criterion_id' not in json.dumps(c)
    assert all(not e['clinical_ground_truth'] and not e['is_model_output'] for e in expected)


def test_time_boundaries_and_evidence_references_are_consistent():
    cases = {c['id']: c for c in read('data/research/feature-cases.json')}
    for e in read('data/research/feature-expectations.json'):
        c = cases[e['case_id']]
        available = {d['id'] for d in c['documents']
                     if datetime.fromisoformat(d['available_at']) <= datetime.fromisoformat(c['review_at'])}
        assert set(e['evidence_document_ids']) <= available
        assert all(datetime.fromisoformat(d['event_at']) <= datetime.fromisoformat(d['available_at'])
                   for d in c['documents'])
    late = cases['feature-v1-03']
    boundary = cases['feature-v1-14']
    assert next(d for d in late['documents'] if d['id'] == 'result')['available_at'] > late['review_at']
    assert next(d for d in boundary['documents'] if d['id'] == 'result')['available_at'] == boundary['review_at']


def test_scope_and_exceptions_are_present_without_claiming_clinical_validity():
    cases = {c['id']: c for c in read('data/research/feature-cases.json')}
    expected = {e['case_id']: e for e in read('data/research/feature-expectations.json')}
    assert cases['feature-v1-08']['age'] == 17
    assert cases['feature-v1-13']['age'] is None
    assert cases['feature-v1-09']['care_setting'] == 'intensive_care'
    assert cases['feature-v1-10']['diagnosis']['code'] == 'I50.9'
    for case_id in ('feature-v1-06', 'feature-v1-07'):
        assert expected[case_id]['expected_status'] == 'requires_expert'
        assert any(d['id'] == 'exception' for d in cases[case_id]['documents'])
    assert cases['feature-v1-12']['source_context'] is None
    assert all(c['source_context'] is None or c['source_context']['valid_for_case_date'] is None
               for c in cases.values())
    mismatch = cases['feature-v1-11']
    assert next(d for d in mismatch['documents'] if d['id'] == 'discharge')['diagnosis_code'] != mismatch['claim_draft']['principal_diagnosis_code']


def test_manifest_matches_the_delivered_files():
    manifest = read('research/feature-packet-manifest.json')
    assert not manifest['feature_executed']
    assert manifest['independent_family_count_added'] == 0
    for name, expected_hash in manifest['files'].items():
        assert hashlib.sha256((ROOT / 'data/research' / name).read_bytes()).hexdigest() == expected_hash
