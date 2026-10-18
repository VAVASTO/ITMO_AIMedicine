from fastapi.testclient import TestClient

from itmo_aimedicine import api
from itmo_aimedicine.config import Settings


def test_ui_flow_does_not_leak_key(monkeypatch):
    monkeypatch.setattr(api, "settings", lambda: Settings(api_key="secret-for-test"))
    client = TestClient(api.app)
    status = client.get("/api/status")
    assert status.status_code == 200 and status.json()["key_configured"] is True
    assert "secret-for-test" not in status.text
    response = client.post("/api/smoke")
    assert response.status_code == 200
    assert response.json()["mode"] == "mock"
    assert response.json()["attempts"] == 0


def test_ui_live_failure_is_visible(monkeypatch):
    monkeypatch.setattr(api, "settings", lambda: Settings(mode="live"))
    response = TestClient(api.app).post("/api/smoke")
    assert response.status_code == 502 and "MISTRAL_API_KEY" in response.json()["detail"]
