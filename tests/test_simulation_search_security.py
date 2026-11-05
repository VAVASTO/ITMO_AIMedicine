import base64
import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from itmo_aimedicine import api
from itmo_aimedicine.config import ROOT
from itmo_aimedicine.longitudinal import cases, snapshot, formal_checks, allowed_action
from itmo_aimedicine.knowledge_search import terms, search
from itmo_aimedicine.simulation import Simulation, simulate


def action(kind,hour): return {'kind':kind,'hour':hour}


def test_actions_change_deadlines_and_repeated_deterioration():
    actions=[action('measure_spo2',0),action('antibiotic_order',2),action('antibiotic_start',4)]
    before=simulate(Simulation(elapsed_hours=54,response='worsening',actions=actions))
    assert before['temporal_facts']['review_since_start_seconds']==50*3600
    assert before['formal_reference']['checks'][2]['status']=='pending'
    actions+=[action('reassessment',54)]
    after=simulate(Simulation(elapsed_hours=54,response='worsening',actions=actions))
    assert [x['status'] for x in after['formal_reference']['checks']]==['met','met','met','attention']
    actions+=[action('treatment_review',54)]
    reviewed=simulate(Simulation(elapsed_hours=54,response='worsening',actions=actions))
    assert reviewed['formal_reference']['checks'][-1]['status']=='met'
    actions+=[action('reassessment',56)]
    repeated=simulate(Simulation(elapsed_hours=56,response='worsening',actions=actions))
    assert repeated['formal_reference']['checks'][-1]['status']=='attention'
    assert repeated['snapshot']['events'][-1]['value']=='worsening' # review does not cure a patient


@pytest.mark.parametrize('actions',[
    [action('antibiotic_start',0)],
    [action('antibiotic_order',3),action('measure_spo2',2)],
    [action('antibiotic_order',2),action('antibiotic_order',3)],
    [action('reassessment',2)],
    [action('antibiotic_order',2),action('antibiotic_start',3),action('treatment_review',4)],
    [action('measure_spo2',100)],
])
def test_impossible_actions_rejected(actions):
    with pytest.raises(ValidationError): Simulation(elapsed_hours=10,actions=actions)


def test_start_before_diagnosis_cannot_choose_assessment_action():
    case=cases()[0].model_copy(deep=True)
    diagnosis=case.events[0].occurred_at
    start=next(e for e in case.events if e.kind=='antibiotic_start')
    start.occurred_at=start.available_at=diagnosis-timedelta(hours=100)
    state=snapshot(case,diagnosis+timedelta(hours=50))
    check=formal_checks(state).checks[2]
    assert check.status=='unknown' and allowed_action(check,state)=='clarify_treatment_start'


def test_search_terms_are_safe_and_bounded():
    assert terms('" OR NOT SELECT *')
    assert len(terms(' '.join(['слово']*100)))==16
    assert terms('и в для')==[]
    assert ['4'] in terms('4 ч')
    assert 'аб' in terms('антибиотиков')[0]
    assert 'госпитализ' in terms('стационаре')[0]


def test_search_endpoint_handles_missing_index(monkeypatch):
    monkeypatch.setattr(api,'search',lambda *args: (_ for _ in ()).throw(FileNotFoundError()))
    assert TestClient(api.app).post('/api/therapy/search',json={'query':'пульсоксиметрия'}).status_code==503


def test_public_demo_fails_closed_without_password(monkeypatch):
    monkeypatch.setenv('PUBLIC_DEMO','1');monkeypatch.delenv('APP_DEMO_PASSWORD',raising=False)
    assert TestClient(api.app).get('/api/therapy/catalog').status_code==503


def test_password_guards_all_routes_and_public_live_is_off(monkeypatch):
    monkeypatch.setenv('PUBLIC_DEMO','1');monkeypatch.setenv('APP_DEMO_PASSWORD','test-password-only')
    monkeypatch.delenv('DEMO_ALLOW_LIVE',raising=False)
    client=TestClient(api.app)
    assert client.get('/').status_code==401
    assert client.get('/api/therapy/catalog',headers={'Authorization':'Basic !!!'}).status_code==401
    headers={'Authorization':'Basic '+base64.b64encode(b'demo:test-password-only').decode()}
    assert client.get('/api/therapy/catalog',headers=headers).json()['live_enabled'] is False
    body={'case_id':'V01','review_at':'2026-11-06T04:30:00+03:00','mode':'live'}
    # Use the catalog time to avoid confounding an invalid selection with access control.
    body['review_at']=next(c for c in api.all_cases() if c.id=='V01').review_times[0].isoformat()
    assert client.post('/api/therapy/evaluate',headers=headers,json=body).status_code==403
    assert client.post('/api/smoke',headers=headers).status_code==403
    headers['Origin']='https://foreign.example'
    assert client.post('/api/therapy/simulate',headers=headers,json={}).status_code==403


def test_ui_job_budget_prevents_provider_call(monkeypatch):
    monkeypatch.setenv('DEMO_DAILY_JOB_LIMIT','0')
    monkeypatch.setattr(api,'settings',lambda: type('Config',(),{'provider':'router','mode':'live'})())
    case=api.all_cases()[0]
    response=TestClient(api.app).post('/api/therapy/evaluate',json={'case_id':case.id,'review_at':case.review_times[0].isoformat(),'mode':'live'})
    assert response.status_code==429


def test_local_smoke_endpoint_also_rejects_cross_site_request(monkeypatch):
    monkeypatch.setattr(api,'settings',lambda: (_ for _ in ()).throw(AssertionError('No key needed')))
    assert TestClient(api.app).post('/api/smoke',headers={'Origin':'https://foreign.example'}).status_code==403


def test_simulator_and_recorded_conditions_need_no_api(monkeypatch):
    monkeypatch.setattr(api,'settings',lambda: (_ for _ in ()).throw(AssertionError('No key needed')))
    client=TestClient(api.app)
    assert client.post('/api/therapy/simulate',json={'elapsed_hours':5}).json()['api_jobs']==0
    case=api.all_cases()[0]
    body={'case_id':case.id,'review_at':case.review_times[0].isoformat(),'mode':'recorded','condition':'v2'}
    assert client.post('/api/therapy/evaluate',json=body).status_code==422
