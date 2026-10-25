import json
import httpx
import pytest
from itmo_aimedicine.config import Settings, FREETHEAI_URL, FREE_GLM_MODELS
from itmo_aimedicine.glm import FreeGLMClient
from itmo_aimedicine.llm import LLMError
from itmo_aimedicine.smoke import run_smoke


def settings(**kwargs):
    return Settings(provider='glm',mode='live',api_key='fake-glm-key',base_url=FREETHEAI_URL,
                    model=FREE_GLM_MODELS[0],**kwargs)


def response(**overrides):
    return {'model':FREE_GLM_MODELS[0],'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'status':'ok','message':'received'})}}],**overrides}


def test_glm_schema_and_secret_boundaries():
    requests=[]
    def handler(r):
        requests.append(r)
        return httpx.Response(200,json=response(usage={'total_tokens':50}))
    result=run_smoke(settings(),transport=httpx.MockTransport(handler))
    assert len(requests)==1 and result.attempts==1
    assert str(requests[0].url)==FREETHEAI_URL+'/chat/completions'
    assert requests[0].headers['authorization']=='Bearer fake-glm-key'
    assert 'fake-glm-key' not in requests[0].content.decode()
    assert result.provider=='freetheai' and result.usage=={'total_tokens':50}
    assert 'fake-glm-key' not in json.dumps(result.as_dict())


@pytest.mark.parametrize('status',[301,401,402,403,429,500,502,503,504])
def test_glm_never_retries_or_follows_paid_redirect(status):
    requests=[]
    def handler(r):
        requests.append(r)
        return httpx.Response(status,text='fake-glm-key private-response',headers={'location':'https://other.example'})
    with pytest.raises(LLMError) as error:
        run_smoke(settings(max_attempts=3),transport=httpx.MockTransport(handler))
    assert len(requests)==1
    assert 'fake-glm-key' not in str(error.value) and 'private-response' not in str(error.value)


@pytest.mark.parametrize('content',['not JSON','{"status":"ok","message":"fake-glm-key"}','{"status":"ok","message":"ok","extra":1}'])
def test_glm_rejects_invalid_or_sensitive_content(content):
    body=response();body['choices'][0]['message']['content']=content
    with pytest.raises(LLMError):run_smoke(settings(),transport=httpx.MockTransport(lambda _:httpx.Response(200,json=body)))


def test_glm_rejects_partial_and_does_not_retry_timeout():
    body=response();body['choices'][0]['finish_reason']='length'
    with pytest.raises(LLMError,match='не завершила'):
        run_smoke(settings(),transport=httpx.MockTransport(lambda _:httpx.Response(200,json=body)))
    calls=[]
    def fail(r):
        calls.append(r);raise httpx.ReadTimeout('private fake-glm-key')
    with pytest.raises(LLMError,match='квоты неизвестен'):
        run_smoke(settings(),transport=httpx.MockTransport(fail))
    assert len(calls)==1


@pytest.mark.parametrize('field,value',[('base_url','http://api.freetheai.org/v1'),('base_url','https://evil.example/v1'),('model','paid/model')])
def test_glm_rejects_other_routes(field,value):
    with pytest.raises(LLMError):FreeGLMClient(settings().model_copy(update={field:value}))


def test_glm_external_env_uses_own_key_without_changing_environment(tmp_path,monkeypatch):
    import itmo_aimedicine.config as config
    monkeypatch.setattr(config,'ROOT',tmp_path)
    monkeypatch.delenv('FREETHEAI_API_KEY',raising=False)
    p=tmp_path/'test.env';p.write_text('FREETHEAI_API_KEY=fake-external-key\nFREETHEAI_GLM_MODEL=fta/zai/glm-5.3\n')
    s=Settings.from_env(provider='glm',env_file=p)
    assert s.api_key.get_secret_value()=='fake-external-key'
    assert s.max_attempts==1 and s.base_url==FREETHEAI_URL
    import os
    assert 'FREETHEAI_API_KEY' not in os.environ


def test_trial_never_sends_expected_labels_and_checks_future_references():
    from itmo_aimedicine.glm_trial import payload_for,assess,ReviewReply
    case={'id':'test','family_id':'family','age':66,'sex':'male','diagnosis':{},'review_at':'2026-10-06T12:00:00+03:00',
          'documents':[{'id':'admission','available_at':'2026-10-01T11:00:00+03:00','text':'input'},
                       {'id':'result','available_at':'2026-10-07T11:00:00+03:00','text':'future'}],
          'claim_draft':{},'care_setting':'general_inpatient','source_context':None}
    expected={'criterion_id':'C02','expected_status':'insufficient_evidence','reason':'target label'}
    payload=payload_for(case,'C02')
    assert set(payload)=={'criterion_id','case'}
    assert not any(x in json.dumps(payload) for x in ('expected_status','target label','family_id'))
    result=ReviewReply(criterion_id='C02',status='insufficient_evidence',explanation='input',available_document_ids=['admission'],evidence_document_ids=['result'],normative_conclusion_allowed=False)
    checked=assess(case,expected,result)
    assert checked['status_match'] and not checked['references_valid'] and not checked['all_automatic_checks']


def test_trial_includes_document_at_exact_time_boundary():
    from itmo_aimedicine.glm_trial import assess,ReviewReply
    case={'review_at':'2026-10-06T12:00:00+03:00','documents':[{'id':'result','available_at':'2026-10-06T12:00:00+03:00'}]}
    expected={'criterion_id':'C02','expected_status':'confirmed'}
    result=ReviewReply(criterion_id='C02',status='confirmed',explanation='available',available_document_ids=['result'],evidence_document_ids=['result'],normative_conclusion_allowed=False)
    assert assess(case,expected,result)['all_automatic_checks']
