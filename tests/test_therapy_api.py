from fastapi.testclient import TestClient

from itmo_aimedicine import api
from itmo_aimedicine.config import Settings


def test_formal_flow_needs_no_key_and_filters_future(monkeypatch):
    monkeypatch.setattr(api, 'settings', lambda: (_ for _ in ()).throw(AssertionError('No settings needed')))
    client = TestClient(api.app)
    data = client.get('/api/therapy/catalog').json()
    case = next(c for c in data['cases'] if c['id'] == 'T07')
    response = client.post('/api/therapy/evaluate',json={'case_id':case['id'],'review_at':case['review_times'][0]})
    assert response.status_code == 200
    assert all(e['kind'] != 'reassessment' for e in response.json()['snapshot']['events'])
    assert response.json()['formal_reference']['checks'][2]['status'] == 'unknown'


def test_cross_site_live_request_is_rejected_before_configuration(monkeypatch):
    monkeypatch.setattr(api, 'settings', lambda: (_ for _ in ()).throw(AssertionError('No config read')))
    response = TestClient(api.app).post('/api/therapy/evaluate',headers={'Origin':'https://untrusted.example'},
        json={'case_id':'T01','review_at':'2026-11-01T08:30:00+03:00','mode':'live'})
    assert response.status_code == 403


def test_live_mode_cannot_fall_back_to_mock(monkeypatch):
    monkeypatch.setattr(api, 'settings', lambda: Settings(mode='mock'))
    response = TestClient(api.app).post('/api/therapy/evaluate',
        json={'case_id':'T01','review_at':'2026-11-01T08:30:00+03:00','mode':'live'})
    assert response.status_code == 503


def test_arbitrary_case_and_unbudgeted_model_are_rejected():
    client = TestClient(api.app)
    body={'case_id':'T01','review_at':'2026-11-01T08:30:00+03:00','model':'paid-model'}
    assert client.post('/api/therapy/evaluate',json=body).status_code == 422
    body.pop('model'); body['case_id']='../../.env'
    assert client.post('/api/therapy/evaluate',json=body).status_code == 422
