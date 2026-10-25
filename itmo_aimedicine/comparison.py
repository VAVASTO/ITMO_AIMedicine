"""Frozen, single-attempt comparison with a persistent per-campaign request cap."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics

from pydantic import BaseModel, ConfigDict, Field

from .config import ROOT, Settings
from .glm import FreeGLMClient
from .glm_trial import ReviewReply, SYSTEM as DEVELOPMENT_SYSTEM, payload_for
from .llm import LLMError, MistralClient

PACKET = ROOT/'data/research/comparison-v1'
CAMPAIGN = ROOT/'reports/live/comparison-v1-2026-10-25'
LIMITS = {'glm':24,'mistral':12}
SYSTEM = DEVELOPMENT_SYSTEM + '''
Дополнение контракта для этого эксперимента:
Если для C05 нет доступной выписки или кода счёта, верни insufficient_evidence.
Сведения из будущих и недатированных документов нельзя использовать даже в объяснении.
Для каждого evidence_document_id добавь в evidence_quotes точную непрерывную цитату из его text.
Для недоступного документа не создавай цитату. Для полей карты вне документов цитата не нужна.
Если документ подтверждает вывод, укажи его в основаниях. Для C02 confirmed основанием служит result.
Пустой список оснований допустим, если вывод основан на отсутствии документа, метаданных или источника.
Не делай выводов о правильности лечения. Оценивается только заданный критерий.'''


class EvidenceQuote(BaseModel):
    model_config = ConfigDict(extra='forbid')
    document_id: str = Field(min_length=1,max_length=60)
    quote: str = Field(min_length=1,max_length=500)


class ComparisonReply(ReviewReply):
    evidence_quotes: list[EvidenceQuote] = Field(max_length=6)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def dump(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def available_documents(case):
    cutoff=datetime.fromisoformat(case['review_at'])
    result=[]
    for doc in case['documents']:
        try:
            when=datetime.fromisoformat(doc.get('available_at') or '')
            if when.tzinfo is not None and when<=cutoff:
                result.append(doc)
        except (ValueError,TypeError):
            continue
    return result


def prepare_payload(case, criterion_id, filtered):
    candidate=deepcopy(case)
    if filtered:
        candidate['documents']=available_documents(case)
    return payload_for(candidate,criterion_id)


def evaluate(case, expected, reply):
    available={d['id']:d for d in available_documents(case)}
    refs=reply.evidence_document_ids
    quotes=reply.evidence_quotes
    quote_ids=[q.document_id for q in quotes]
    text=reply.explanation.casefold()
    markers=[term for term in expected['forbidden_future_markers'] if term.casefold() in text]
    checks={
        'criterion_match':reply.criterion_id==expected['criterion_id'],
        'status_match':reply.status==expected['expected_status'],
        'availability_match':set(reply.available_document_ids)==set(available) and len(reply.available_document_ids)==len(available),
        'references_valid':set(refs)<=set(available) and len(refs)==len(set(refs)),
        'required_evidence_present':set(expected['required_evidence_ids'])<=set(refs),
        'quotes_valid':set(quote_ids)==set(refs) and len(quote_ids)==len(set(quote_ids)) and all(q.document_id in available and q.quote in available[q.document_id]['text'] for q in quotes),
        'required_terms_present':all(term.casefold() in text for term in expected['required_explanation_terms']),
        'no_flagged_future_markers':not markers,
        'normative_conclusion_blocked':reply.normative_conclusion_allowed is False,
    }
    return {**checks,'all_automatic_checks':all(checks.values()),'flagged_future_markers':markers}


def reserve_attempt(folder, provider, case_id, condition):
    """A durable reservation counts even if the connection outcome is unknown."""
    folder.mkdir(parents=True,exist_ok=True)
    limit=LIMITS[provider]
    for index in range(1,limit+1):
        path=folder/f'{provider}-{index:02d}.json'
        try:
            with path.open('x') as stream:
                json.dump({'reserved_at':utc_now(),'provider':provider,'case_id':case_id,'condition':condition},stream)
            return path
        except FileExistsError:
            continue
    raise RuntimeError(f'{provider}: request budget exhausted')


def plan_rows(cases, labels):
    by_id={e['case_id']:e for e in labels}
    rows=[]
    for i,case in enumerate(cases):
        # Alternate paired GLM order; rotate Mistral position to reduce order bias.
        pair=['glm_full','glm_filtered'] if i%2==0 else ['glm_filtered','glm_full']
        conditions=pair+['mistral_filtered'] if i%2==0 else ['mistral_filtered']+pair
        for condition in conditions:
            rows.append({'case':case,'expected':by_id[case['id']], 'condition':condition,
                         'provider':condition.split('_')[0], 'filtered':condition.endswith('_filtered')})
    return rows


def specification():
    cases=json.loads((PACKET/'cases.json').read_text())
    labels=json.loads((PACKET/'expectations.json').read_text())
    if len(cases)!=12 or len(labels)!=12 or len({c['family_id'] for c in cases})!=12:
        raise ValueError('Expected twelve authored histories')
    if not all(c['synthetic'] and not c['expert_reviewed'] for c in cases):
        raise ValueError('Only unreviewed synthetic cases are allowed')
    return cases,labels


def manifest():
    return {'experiment_id':'comparison-v1-2026-10-25','created_at':utc_now(),'purpose':'frozen_engineering_pilot_not_clinical_validation',
            'request_limits':LIMITS,'automatic_retries':0,'temperature':0,'max_tokens':1024,
            'models':{'glm':'fta/zai/glm-5.3','mistral':'ministral-8b-2512'},
            'cases_sha256':hashlib.sha256((PACKET/'cases.json').read_bytes()).hexdigest(),
            'expectations_sha256':hashlib.sha256((PACKET/'expectations.json').read_bytes()).hexdigest(),
            'system_sha256':hashlib.sha256(SYSTEM.encode()).hexdigest(),'schema':ComparisonReply.model_json_schema(),
            'metric_priority':['status_and_grounding_errors','latency','provider_reported_tokens'],
            'limitations':['12 authored histories, no independent clinical labels or repeated model runs.',
                          'GLM uses prompt JSON; Mistral additionally enforces provider JSON Schema. Comparison concerns configured pipelines.',
                          'Exact future markers are a lower-bound detector; every explanation also needs manual review.',
                          'No hybrid retrieval, OCR, end-to-end audit or clinical quality validation.']}


def freeze():
    cases,labels=specification()
    path=PACKET/'manifest.json'
    if path.exists():
        raise FileExistsError('The experiment is already frozen')
    dump(path,manifest())
    (PACKET/'system-prompt.txt').write_text(SYSTEM+'\n')
    print('Frozen 12 cases, labels, prompt, schema and request limits; no API calls')


def run(env_file):
    cases,labels=specification()
    fixed=json.loads((PACKET/'manifest.json').read_text())
    current=manifest()
    for key in current:
        if key!='created_at' and fixed[key]!=current[key]:
            raise ValueError(f'Frozen experiment mismatch: {key}')
    # One fixed campaign directory prevents accidental reruns under another name.
    CAMPAIGN.mkdir(parents=True,exist_ok=False)
    settings={
        'glm':Settings.from_env(provider='glm',env_file=env_file).model_copy(update={'mode':'live','model':fixed['models']['glm'],'temperature':0,'max_tokens':1024,'max_attempts':1}),
        'mistral':Settings.from_env(provider='mistral').model_copy(update={'mode':'live','model':fixed['models']['mistral'],'temperature':0,'max_tokens':1024,'max_attempts':1,'timeout_seconds':120}),
    }
    if not all(s.api_key.get_secret_value() for s in settings.values()):
        raise ValueError('Both provider keys must be set; no requests sent')
    clients={'glm':FreeGLMClient(settings['glm']),'mistral':MistralClient(settings['mistral'])}
    schema_suffix='\nReturn only a JSON object matching this schema, without Markdown: '+json.dumps(ComparisonReply.model_json_schema(),ensure_ascii=False)
    records=[]
    stopped=set()
    for row in plan_rows(cases,labels):
        provider=row['provider'];case=row['case'];condition=row['condition']
        record={'case_id':case['id'],'condition':condition,'provider':provider}
        if provider in stopped:
            record.update(state='not_attempted',reason='provider_stopped_after_first_error')
            records.append(record)
            continue
        payload=prepare_payload(case,row['expected']['criterion_id'],row['filtered'])
        dump(CAMPAIGN/f"{case['id']}-{condition}-input.json",payload)
        reserve_attempt(CAMPAIGN/'reservations',provider,case['id'],condition)
        record.update(state='started',started_at=utc_now(),attempts=1,input_sha256=hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest())
        out=CAMPAIGN/f"{case['id']}-{condition}-result.json"
        dump(out,record)
        try:
            # Both models see the same schema text. Mistral also has native schema enforcement.
            reply=clients[provider].complete(SYSTEM+(schema_suffix if provider=='mistral' else ''),payload,ComparisonReply)
            safe=json.dumps(reply.as_dict(),ensure_ascii=False)
            if any(s.api_key.get_secret_value() in safe for s in settings.values()):
                raise LLMError('Sensitive response rejected')
            record.update(**reply.as_dict(),state='completed',checks=evaluate(case,row['expected'],reply.result))
        except LLMError as error:
            record.update(state='failed',error=str(error))
            stopped.add(provider)
        record['finished_at']=utc_now()
        dump(out,record);records.append(record)
        dump(CAMPAIGN/'results.json',{'manifest':fixed,'records':records})
        print(json.dumps({'case':case['id'],'condition':condition,'state':record['state'],'checks':record.get('checks'),'error':record.get('error')},ensure_ascii=False),flush=True)
    report={'manifest':fixed,'finished_at':utc_now(),'records':records,'conditions':{}}
    for condition in ('glm_full','glm_filtered','mistral_filtered'):
        group=[r for r in records if r['condition']==condition]
        done=[r for r in group if r['state']=='completed']
        report['conditions'][condition]={'planned':len(group),'attempted':sum(r['state']!='not_attempted' for r in group),'completed':len(done),
            'status_matches':sum(r['checks']['status_match'] for r in done),'all_automatic_checks_passed':sum(r['checks']['all_automatic_checks'] for r in done),
            'latency_median_ms':statistics.median(r['latency_ms'] for r in done) if done else None,
            'total_tokens_reported':sum(r['usage'].get('total_tokens',0) for r in done)}
    dump(CAMPAIGN/'results.json',report)
    print(json.dumps(report['conditions'],ensure_ascii=False),flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--freeze',action='store_true')
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--env-file',type=Path)
    args=parser.parse_args()
    if args.freeze and not args.live:
        freeze()
    elif args.live and not args.freeze and args.env_file:
        run(args.env_file)
    else:
        parser.error('Choose --freeze or --live --env-file PATH')


if __name__=='__main__':
    main()
