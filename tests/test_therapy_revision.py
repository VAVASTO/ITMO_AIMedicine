import json
from datetime import timedelta

import pytest

from itmo_aimedicine.config import ROOT
from itmo_aimedicine.longitudinal import Case, snapshot, formal_checks, allowed_action
from itmo_aimedicine.therapy_v2 import temporal_facts, payload, run_pipeline


def revision_cases():
    return [Case.model_validate(x) for x in json.loads((ROOT/'data/therapy/revision-cases.json').read_text())]


def test_new_labels_are_independent_of_model_input():
    labels = json.loads((ROOT/'data/therapy/revision-expectations.json').read_text())['snapshots']
    for case, label in zip(revision_cases(), labels):
        state = snapshot(case, case.review_times[0])
        checks = formal_checks(state).checks
        assert {c.rule_id:c.status for c in checks} == label['statuses']
        assert {c.rule_id:allowed_action(c,state) for c in checks if allowed_action(c,state)} == label['actions']
        assert set(payload(state)) == {'state','source_cards','temporal_facts'}


def test_offsets_and_inclusive_boundaries():
    case = revision_cases()[0]
    facts = temporal_facts(snapshot(case, case.review_times[0]))
    assert facts['order_since_diagnosis_seconds'] == 14400
    assert facts['review_since_start_seconds'] == 259200
    assert not facts['assessment_intervals']


def test_one_second_late_and_unavailable_record():
    case = revision_cases()[1]
    facts = temporal_facts(snapshot(case, case.review_times[0]))
    assert facts['order_since_diagnosis_seconds'] == 14401
    assert facts['review_since_start_seconds'] == 259201
    assert not facts['assessment_intervals']


def test_absent_start_stays_null():
    case = revision_cases()[3]
    facts = temporal_facts(snapshot(case, case.review_times[0]))
    assert facts['first_start_id'] is None and facts['review_since_start_seconds'] is None
    assert facts['latest_worsening_id'] is None


def test_later_deterioration_invalidates_old_review():
    case = revision_cases()[5]
    facts = temporal_facts(snapshot(case, case.review_times[0]))
    assert facts['latest_worsening_id'].endswith('56')
    assert facts['reviews_after_latest_worsening'] == []


def test_future_fact_rejected_if_caller_bypasses_snapshot():
    case = revision_cases()[1]
    state = snapshot(case, case.review_times[0])
    state['events'].append(case.events[-1].model_dump(mode='json'))
    with pytest.raises(ValueError): temporal_facts(state)


def test_audit_does_not_receive_the_plan():
    from types import SimpleNamespace
    case = revision_cases()[6]
    class Provider:
        def __init__(self): self.inputs=[]
        def complete(self, prompt, data, schema):
            self.inputs.append(data)
            result = schema.model_validate({'recommendations':[]} if len(self.inputs)==1
                                           else formal_checks(data['state']).model_dump())
            return SimpleNamespace(result=result,as_dict=lambda:{'result':result.model_dump()})
    provider = Provider()
    result = run_pipeline(case,case.review_times[0],provider)
    assert len(provider.inputs)==2 and provider.inputs[0]==provider.inputs[1]
    assert 'draft_plan' not in provider.inputs[1]
    assert result['review_required'] is False
