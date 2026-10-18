import json

import httpx
import pytest
from pydantic import SecretStr

from itmo_aimedicine.config import Settings
from itmo_aimedicine.llm import LLMError, MistralClient, get_provider
from itmo_aimedicine.smoke import PAYLOAD, SYSTEM, SmokeReply, run_smoke

KEY = "fake-test-key"


def reply(**overrides):
    body = {"model": "model-resolved-by-server", "choices": [{"finish_reason": "stop",
            "message": {"content": '{"status":"ok","message":"received"}'}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}}
    body.update(overrides)
    return body


def call(handler, **options):
    settings = Settings(api_key=KEY, **options)
    client = MistralClient(settings, transport=httpx.MockTransport(handler), sleep=lambda _: None)
    return client.complete(SYSTEM, PAYLOAD, SmokeReply)


def test_structured_request_and_usage():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=reply())
    result = call(handler)
    request = requests[0]
    assert str(request.url) == "https://api.mistral.ai/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    body = json.loads(request.content)
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
    assert result.model == "model-resolved-by-server"
    assert result.usage["total_tokens"] == 30
    assert result.attempts == 1
    assert KEY not in json.dumps(result.as_dict())


def test_missing_key_does_not_send_request():
    client = MistralClient(Settings(), transport=httpx.MockTransport(lambda _: pytest.fail("network")))
    with pytest.raises(LLMError, match="MISTRAL_API_KEY"):
        client.complete(SYSTEM, PAYLOAD, SmokeReply)


@pytest.mark.parametrize("url", ["http://api.mistral.ai/v1", "https://other.example/v1", "https://api.mistral.ai.evil/v1"])
def test_other_endpoints_rejected(url):
    with pytest.raises(LLMError, match="официальный"):
        MistralClient(Settings(base_url=url))


@pytest.mark.parametrize("status", [301, 401, 402, 403, 404, 500])
def test_errors_do_not_leak_provider_response_or_retry(status):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(status, text=f"private-body-{KEY}", headers={"location": "https://other.example"})
    with pytest.raises(LLMError) as error:
        call(handler)
    assert len(requests) == 1
    assert "private-body" not in str(error.value) and KEY not in str(error.value)


def test_transient_error_is_bounded():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(503)
    with pytest.raises(LLMError, match="503"):
        call(handler)
    assert len(requests) == 3


def test_rate_limit_then_success():
    responses = iter([httpx.Response(429, headers={"retry-after": "not-a-number"}), httpx.Response(200, json=reply())])
    assert call(lambda _: next(responses)).attempts == 2


def test_zero_model_quota_stops_immediately():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(429, headers={"x-ratelimit-limit-req-minute": "0"})
    with pytest.raises(LLMError, match="равна нулю"):
        call(handler)
    assert len(requests) == 1


def test_network_error_does_not_duplicate_ambiguous_request():
    requests = []
    def handler(request):
        requests.append(request)
        raise httpx.ReadTimeout(f"private-body-{KEY}")
    with pytest.raises(LLMError) as error:
        call(handler)
    assert len(requests) == 1 and KEY not in str(error.value)


@pytest.mark.parametrize("content", ["bad JSON", '{"status":"failed","message":"x"}',
    '{"status":"ok","message":"x","extra":"bad"}', '{"status":"ok","message":""}'])
def test_invalid_structured_reply_is_rejected(content):
    body = reply()
    body["choices"][0]["message"]["content"] = content
    with pytest.raises(LLMError, match="схеме"):
        call(lambda _: httpx.Response(200, json=body))


@pytest.mark.parametrize("reason", ["length", "tool_calls", "content_filter"])
def test_partial_or_nonfinal_reply_is_rejected(reason):
    body = reply()
    body["choices"][0]["finish_reason"] = reason
    with pytest.raises(LLMError, match="не завершил"):
        call(lambda _: httpx.Response(200, json=body))


def test_text_chunks_supported():
    body = reply()
    body["choices"][0]["message"]["content"] = [{"type": "text", "text": '{"status":"ok",'},
                                               {"type": "text", "text": '"message":"chunks"}'}]
    assert call(lambda _: httpx.Response(200, json=body)).result.message == "chunks"


def test_mock_never_contacts_provider_even_with_key():
    result = run_smoke(Settings(api_key=SecretStr(KEY)), transport=httpx.MockTransport(lambda _: pytest.fail("network")))
    assert result.mode == "mock" and result.provider == "mock" and result.attempts == 0


def test_live_does_not_fall_back_to_mock():
    with pytest.raises(LLMError):
        run_smoke(Settings(mode="live"))


def test_gemini_is_explicitly_deferred():
    with pytest.raises(LLMError, match="Gemini отложен"):
        get_provider(Settings(provider="gemini"))
