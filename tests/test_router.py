import json

import httpx
import pytest

from itmo_aimedicine.config import ROUTER_URL, Settings
from itmo_aimedicine.llm import LLMError
from itmo_aimedicine.router import RouterClient, response_schema, normalize_json_wrapper
from itmo_aimedicine.smoke import SmokeReply


def client(handler, **kwargs):
    now = [0.0]
    def sleep(seconds):
        now[0] += seconds
    settings = Settings(provider="router", api_key="rtr_fake_test_key", model="gemini-3.5-flash-lite",
                        base_url=ROUTER_URL, job_timeout_seconds=30, **kwargs)
    return RouterClient(settings, transport=httpx.MockTransport(handler), sleep=sleep, clock=lambda: now[0])


def done(**overrides):
    return {"id": "job_test", "model": "gemini-3.5-flash-lite", "status": "done", "result": {
        "text": '{"status":"ok","message":"received"}', "finishReason": "STOP",
        "usage": {"input": 10, "output": 5, "total": 15}}, **overrides}


def test_submit_once_poll_and_validate():
    requests = []
    def handler(request):
        requests.append(request)
        if request.method == "POST":
            body = json.loads(request.content)
            assert body["fallback"] is False
            assert body["config"]["responseSchema"]["properties"]["status"]["enum"] == ["ok"]
            return httpx.Response(202, json={"id": "job_test", "status": "queued"})
        return httpx.Response(200, json=done() if len(requests) == 3 else done(status="running"))
    result = client(handler).complete("system", {"test": True}, SmokeReply)
    assert result.job_id == "job_test" and result.attempts == 1 and result.latency_ms == 20000
    assert result.usage["total"] == 15
    assert [r.method for r in requests] == ["POST", "GET", "GET"]
    assert "rtr_fake" not in json.dumps(result.as_dict())


@pytest.mark.parametrize("changed", [
    {"fallback": {"served_by": "other"}}, {"model": "other"}, {"id": "job_other"},
    {"status": "failed"}, {"status": "blocked"}, {"status": "unknown"},
    {"result": {"text": '{"status":"ok","message":"x"}', "finishReason": "MAX_TOKENS"}},
    {"result": {"text": "not JSON", "finishReason": "STOP"}},
])
def test_bad_or_substituted_results_rejected(changed):
    def handler(request):
        return httpx.Response(202, json={"id": "job_test"}) if request.method == "POST" else httpx.Response(200, json=done(**changed))
    with pytest.raises(LLMError):
        client(handler).complete("s", {}, SmokeReply)


def test_timeout_keeps_job_id_and_never_resubmits():
    calls = []
    def handler(request):
        calls.append(request.method)
        return httpx.Response(202, json={"id": "job_test"}) if request.method == "POST" else httpx.Response(200, json=done(status="queued"))
    with pytest.raises(LLMError, match="job_test"):
        client(handler).complete("s", {}, SmokeReply)
    assert calls == ["POST", "GET", "GET", "GET"]


@pytest.mark.parametrize("status", [301, 401, 403, 413, 429, 500])
def test_http_error_does_not_disclose_body_or_retry(status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="secret-and-patient-data", headers={"Location": "https://other.example"})
    with pytest.raises(LLMError) as e:
        client(handler).complete("s", {}, SmokeReply)
    assert len(calls) == 1 and "secret-and" not in str(e.value)


def test_schema_reference_nullable_and_order():
    value = response_schema({"type": "object", "$defs": {"Item": {"type": "string"}},
        "properties": {"item": {"anyOf": [{"$ref": "#/$defs/Item"}, {"type": "null"}]}}, "required": ["item"]})
    assert value["properties"]["item"] == {"type": "STRING", "nullable": True}
    assert value["propertyOrdering"] == ["item"]


def test_key_file_never_in_error(tmp_path, monkeypatch):
    path = tmp_path / "key.txt"
    path.write_text("rtr_test_secret\n")
    monkeypatch.setenv("ANTEI_ROUTER_KEY_FILE", str(path))
    monkeypatch.delenv("ANTEI_ROUTER_API_KEY", raising=False)
    settings = Settings.from_env(provider="router")
    assert settings.api_key.get_secret_value() == "rtr_test_secret"
    assert "rtr_test_secret" not in repr(settings)


@pytest.mark.parametrize('count,accepted', [(16, False), (17, True), (18, False)])
def test_unbounded_provider_schema_still_validates_exact_audit_length(count, accepted):
    from itmo_aimedicine.therapy_expansion import ModelAudit
    checks = [dict(rule_id='Q01', status='unknown', explanation='test',
                   evidence_ids=[], source_ids=['WORKFLOW']) for _ in range(count)]

    def handler(request):
        if request.method == 'POST':
            array = json.loads(request.content)['config']['responseSchema']['properties']['checks']
            assert 'minItems' not in array and 'maxItems' not in array
            assert array['items']['properties']['status']['enum']
            return httpx.Response(202, json={'id': 'job_test'})
        return httpx.Response(200, json=done(result={'text': json.dumps({'checks': checks}), 'finishReason': 'STOP'}))

    router = client(handler)
    router.schema_array_bounds = False
    if accepted:
        assert len(router.complete('test', {}, ModelAudit).result.checks) == 17
    else:
        with pytest.raises(LLMError):
            router.complete('test', {}, ModelAudit)
    # The normal mode and the original local schema keep their exact length.
    assert response_schema(ModelAudit.model_json_schema())['properties']['checks']['maxItems'] == 17


@pytest.mark.parametrize('text',[
    '{"status":"ok","message":"x"}\n```',
    '```json\n{"status":"ok","message":"x"}\n```',
    '```\n{"status":"ok","message":"x"}\n```',
])
def test_ui_cleanup_preserves_json_and_strict_experiment_rejects_fences(text):
    def handler(request):
        return httpx.Response(202,json={'id':'job_test'}) if request.method=='POST' else httpx.Response(200,json=done(result={'text':text,'finishReason':'STOP'}))
    strict=client(handler)
    with pytest.raises(LLMError): strict.complete('s',{},SmokeReply)
    tolerant=client(handler);tolerant.normalize_wrapper=True
    completion=tolerant.complete('s',{},SmokeReply)
    assert completion.result.message=='x'
    assert completion.as_dict()['format_cleanup']=='markdown_fence_removed'


@pytest.mark.parametrize('text',[
    'Here is your answer: {"status":"ok","message":"x"}\n```',
    '{"status":"ok","message":"x"}\n{"extra":true}\n```',
    '```json\n{"status":"wrong","message":"x"}\n```',
])
def test_cleanup_does_not_hide_extra_text_objects_or_invalid_fields(text):
    cleaned,_=normalize_json_wrapper(text)
    with pytest.raises(ValueError): SmokeReply.model_validate_json(cleaned)
