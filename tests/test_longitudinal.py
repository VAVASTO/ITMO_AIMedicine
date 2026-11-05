import json
from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from itmo_aimedicine.config import ROOT
from itmo_aimedicine.llm import LLMError
from itmo_aimedicine.longitudinal import Audit, Case, Event, cards, cases, formal_checks, snapshot, validate_links


def test_independent_scenario_expectations():
    indexed = {c.id: c for c in cases()}
    expected = json.loads((ROOT / 'data/therapy/expectations.json').read_text())['snapshots']
    for item in expected:
        state = snapshot(indexed[item['case_id']], datetime.fromisoformat(item['review_at']))
        actual = {c.rule_id: c.status for c in formal_checks(state).checks}
        assert actual == item['statuses'], item['case_id']


def test_late_and_future_documents_are_physically_excluded():
    for cid in ('T07', 'T08'):
        case = next(c for c in cases() if c.id == cid)
        state = snapshot(case, case.review_times[0])
        assert not any(e['kind'] == 'reassessment' for e in state['events'])
        assert 'title' not in state and 'review_times' not in state
        assert 'expected' not in json.dumps(state)


def test_order_and_start_are_distinct_clocks():
    case = cases()[0].model_copy(deep=True)
    start = next(e for e in case.events if e.kind == 'antibiotic_start')
    start.occurred_at += timedelta(hours=10)
    start.available_at = start.occurred_at
    state = snapshot(case, case.review_times[-1])
    checks = {c.rule_id: c.status for c in formal_checks(state).checks}
    assert checks['CAP02'] == 'met' and checks['CAP03'] == 'pending'


def test_boundary_and_missing_record_are_not_omission():
    case = cases()[0]
    diagnosis = case.events[0].occurred_at
    case = case.model_copy(update={'events': [case.events[0]]})
    at_four = formal_checks(snapshot(case, diagnosis + timedelta(hours=4)))
    after_four = formal_checks(snapshot(case, diagnosis + timedelta(hours=4, seconds=1)))
    assert at_four.checks[1].status == 'pending'
    assert after_four.checks[1].status == 'unknown'


def test_repeat_deterioration_requires_new_review():
    case = next(c for c in cases() if c.id == 'T06').model_copy(deep=True)
    moment = case.review_times[0]
    case.events.append(Event(id='new', kind='reassessment', occurred_at=moment,
                             available_at=moment, value='worsening'))
    assert formal_checks(snapshot(case, moment)).checks[-1].status == 'attention'


@pytest.mark.parametrize('field,value', [('age', 17), ('ward', 'icu'), ('severity', 'severe')])
def test_scope_is_enforced(field, value):
    case = cases()[0].model_copy(update={field: value})
    assert {c.status for c in formal_checks(snapshot(case, case.review_times[-1])).checks} == {'not_applicable'}


def test_fake_and_future_citations_are_rejected():
    case = cases()[0]
    state = snapshot(case, case.review_times[0])
    result = formal_checks(state)
    result.checks[0].evidence_ids = [case.events[-1].id]
    with pytest.raises(LLMError):
        validate_links(result, state, cards())

    result = formal_checks(state)
    result.checks[0].source_id = 'made-up'
    with pytest.raises(LLMError):
        validate_links(result, state, cards())


def test_duplicate_rule_cannot_replace_missing_rule_even_in_valid_json():
    case=cases()[0]
    state=snapshot(case,case.review_times[-1])
    result=formal_checks(state)
    result.checks[3]=result.checks[1].model_copy(deep=True)
    # A parsed JSON object with four rows can still contain CAP02 twice and omit CAP04.
    result=Audit.model_validate_json(result.model_dump_json())
    with pytest.raises(LLMError,match='набор правил'):
        validate_links(result,state,cards())


def test_invalid_timestamps_and_duplicate_ids_rejected():
    raw = cases()[0].model_dump(mode='json')
    raw['events'].append(raw['events'][0])
    with pytest.raises(ValidationError):
        Case.model_validate(raw)
    with pytest.raises(ValidationError):
        Event(id='x', kind='spo2', occurred_at='2026-11-01T10:00:00',
              available_at='2026-11-01T10:00:00', value='95')
