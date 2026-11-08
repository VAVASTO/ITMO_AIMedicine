from datetime import timedelta
import json
import pytest
from fastapi.testclient import TestClient
from itmo_aimedicine import therapy_expansion as core
from itmo_aimedicine.api import app
from itmo_aimedicine.llm import LLMError


def statuses(case,at=None):
    return {r['rule_id']:r['status'] for r in core.check(core.snapshot(case,at or case.review_times[2]))['checks']}


@pytest.mark.parametrize('case',core.cases(),ids=lambda c:c.id)
def test_independent_author_expectations(case):
    rows=json.loads((core.ROOT/'data/therapy-expansion/expectations.json').read_text())['snapshots']
    expected=next(r for r in rows if r['case_id']==case.id)
    assert statuses(case)==expected['statuses']


def test_future_availability_and_title_do_not_leak():
    case=next(c for c in core.cases() if c.id=='M01-delayed')
    state=core.snapshot(case,case.review_times[2])
    assert 'title' not in state and 'provenance' not in state and 'review_times' not in state
    assert not any(e['kind']=='lab' for e in state['events'])
    assert statuses(case)['Q05']=='unknown'
    assert statuses(case,case.review_times[3])['Q05']=='met'
    assert 'statuses' not in json.dumps(core.payload(state))


@pytest.mark.parametrize('hours,expected',[(3.999,'met'),(4,'met'),(4.001,'attention')])
def test_antibiotic_order_boundary(hours,expected):
    case=core.cases()[0].model_copy(deep=True)
    order=next(e for e in case.events if e.kind=='order')
    order.occurred_at=order.available_at=case.admission_at+timedelta(hours=hours)
    assert statuses(case)['Q11']==expected


@pytest.mark.parametrize('hours,expected',[(47.99,'unknown'),(48,'met'),(72,'met'),(72.01,'attention')])
def test_response_window_from_administration(hours,expected):
    case=core.cases()[0].model_copy(deep=True)
    start=next(e for e in case.events if e.kind=='administration')
    response=next(e for e in case.events if e.kind=='reassessment')
    response.occurred_at=response.available_at=start.occurred_at+timedelta(hours=hours)
    assert statuses(case)['Q13']==expected


def test_late_allergy_entry_cannot_retroactively_make_order_safe():
    case=core.cases()[0].model_copy(deep=True)
    allergy=next(e for e in case.events if e.kind=='allergy_review')
    allergy.available_at=case.admission_at+timedelta(hours=5)
    result=statuses(case)
    assert result['Q03']=='attention' and result['Q08']=='unknown'


def test_allergy_exact_conflict_and_unknown_are_distinct():
    case=core.cases()[0].model_copy(deep=True)
    allergy=next(e for e in case.events if e.kind=='allergy_review')
    allergy.value='known';allergy.details={'substances':'antibiotic'}
    assert statuses(case)['Q08']=='attention'
    allergy.details={}
    assert statuses(case)['Q08']=='unknown'


def test_dm2_hba1c_window_not_one_year():
    case=next(c for c in core.cases() if c.id=='M05-complete').model_copy(deep=True)
    event=next(e for e in case.events if e.code=='hba1c')
    event.occurred_at=event.available_at=case.review_times[2]-timedelta(days=91)
    assert statuses(case)['Q05']=='unknown'
    event.occurred_at=event.available_at=case.review_times[2]-timedelta(days=90)
    assert statuses(case)['Q05']=='met'


def test_unlinked_reassessment_does_not_complete_plan():
    case=core.cases()[0].model_copy(deep=True)
    next(e for e in case.events if e.kind=='reassessment').details={}
    assert statuses(case)['Q15']=='unknown'


def test_administration_must_match_drug_and_available_order():
    case=core.cases()[0].model_copy(deep=True)
    next(e for e in case.events if e.kind=='administration').code='different-drug'
    assert statuses(case)['Q12']=='attention'


def test_exception_is_local_and_minor_out_of_scope():
    case=core.cases()[0].model_copy(deep=True)
    case.events.append(core.Event(id='exception',kind='exception',code='Q11',occurred_at=case.admission_at,available_at=case.admission_at))
    assert statuses(case)['Q11']=='unknown' and statuses(case)['Q13']=='met'
    case.age=17
    assert set(statuses(case).values())=={'not_applicable'}


def test_different_offsets_same_instant():
    case=core.cases()[0].model_copy(deep=True)
    before=statuses(case)
    from datetime import timezone
    for e in case.events:e.occurred_at=e.occurred_at.astimezone(timezone.utc)
    assert statuses(case)==before


def test_api_simulation_is_ephemeral_and_rejects_future(monkeypatch):
    monkeypatch.delenv('PUBLIC_DEMO',raising=False);monkeypatch.delenv('APP_DEMO_PASSWORD',raising=False)
    client=TestClient(app);c=next(c for c in core.cases() if c.id=='M01-gap')
    body={'case_id':c.id,'review_at':c.review_times[2].isoformat()}
    event=dict(id='ui1',kind='treatment_review',occurred_at=body['review_at'],available_at=body['review_at'],value='documented')
    result=client.post('/api/multi/evaluate',json={**body,'additions':[event]})
    assert result.status_code==200
    assert {'rule_id':'Q14','before':'attention','after':'met'} in result.json()['changes']
    assert not client.post('/api/multi/evaluate',json=body).json()['changes']
    event['available_at']=(c.review_times[2]+timedelta(days=1)).isoformat()
    assert client.post('/api/multi/evaluate',json={**body,'additions':[event]}).status_code==422


def test_synthea_kept_outside_russian_scope():
    cases=json.loads((core.ROOT/'data/therapy-expansion/synthea-cases.json').read_text())
    assert {c['primary'] for c in cases}=={'CAP','COPD','HTN','HF','DM2'}
    for value in cases:
        case=core.Encounter.model_validate(value)
        assert case.ward=='other'
        assert set(statuses(case,case.review_times[-1]).values())=={'not_applicable'}
        assert not any(e.kind=='administration' for e in case.events)
        assert not any(e.kind=='allergy_review' and e.value=='none_known' for e in case.events)


def test_model_cannot_cite_future_or_foreign_source():
    case=core.cases()[0];state=core.snapshot(case,case.review_times[2])
    row=dict(rule_id='Q11',action='review_record',explanation='Проверить запись',evidence_ids=['nonexistent'],source_ids=['CAP2024'])
    with pytest.raises(LLMError):core.validate_output(core.ModelPlan(recommendations=[row]),state)
    row.update(evidence_ids=[],source_ids=['HF2024'])
    with pytest.raises(LLMError):core.validate_output(core.ModelPlan(recommendations=[row]),state)


def test_comorbid_profile_adds_tests_and_uses_stricter_window():
    case=next(c for c in core.cases() if c.id=='M03-complete').model_copy(deep=True)
    creatinine=next(e for e in case.events if e.code=='creatinine')
    creatinine.occurred_at=creatinine.available_at=case.admission_at-timedelta(days=30)
    assert statuses(case)['Q05']=='met'
    case.comorbidities=['HF']
    # The old creatinine is no longer sufficient for the current-admission HF contract.
    assert statuses(case)['Q05']=='unknown'
    assert statuses(case)['Q06']=='unknown'  # Echo is also needed in the chosen subset.


def test_recorded_plan_disagreement_exposed(monkeypatch):
    monkeypatch.delenv('PUBLIC_DEMO',raising=False);monkeypatch.delenv('APP_DEMO_PASSWORD',raising=False)
    c=next(c for c in core.cases() if c.id=='M01-gap')
    result=TestClient(app).post('/api/multi/evaluate',json={'case_id':c.id,'review_at':c.review_times[2].isoformat()}).json()
    record=next(r for r in result['recorded'] if r['model']=='gemini-3.5-flash-lite')
    assert record['plan_comparison']['missing']==['Q15']
    assert record['plan_comparison']['extra']==['Q09']


def test_gemma_repeat_keeps_original_failure_visible(monkeypatch):
    monkeypatch.delenv('PUBLIC_DEMO',raising=False);monkeypatch.delenv('APP_DEMO_PASSWORD',raising=False)
    case=next(c for c in core.cases() if c.id=='M01-gap')
    data=TestClient(app).post('/api/multi/evaluate',json={
        'case_id':case.id,'review_at':case.review_times[2].isoformat()}).json()
    rows={r['series_id']:r for r in data['recorded'] if r['model']=='gemma-4-31b-it'}
    assert rows['therapy-expansion']['roles']['audit']['status']=='error'
    assert rows['therapy-expansion-gemma-compatible']['roles']['audit']['status']=='ok'
    assert rows['therapy-expansion']['max_output_tokens']==8192
    assert rows['therapy-expansion-gemma-compatible']['max_output_tokens']==4096
