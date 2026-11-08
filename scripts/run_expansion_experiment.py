"""Five fixed cases x two models x two independent roles = at most 20 free jobs."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import httpx

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from itmo_aimedicine import therapy_expansion as core
from itmo_aimedicine.config import ROOT,Settings
from itmo_aimedicine.llm import LLMError
from itmo_aimedicine.router import RouterClient

OUT=ROOT/'reports/therapy-expansion'
MODELS=('gemini-3.5-flash-lite','gemma-4-31b-it')
CASE_IDS=('M01-gap','M02-complete','M03-delayed','M04-gap','M05-complete')
ROLES={'audit':core.ModelAudit,'recommend':core.ModelPlan}


def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def write(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)


def prompt(role):
    return core.PROMPT+'\n'+('Audit every rule Q01..Q17 exactly once in order.' if role=='audit' else
      'Recommend exactly one safe action for every applicable unknown/attention/pending rule, none for met/not_applicable. Use review_record for unknown, request_clinician_review for attention, schedule_review for pending. These are documentation-review tasks, not treatment orders.')


def run(task):
    model,case,role=task;path=OUT/f'{model}--{case.id}--{role}.json'
    if path.exists():print(path.name,'already attempted; no retry',flush=True);return
    state=core.snapshot(case,case.review_times[2]);data=core.payload(state)
    record=dict(model=model,case_id=case.id,role=role,review_at=state['review_at'],payload=data,
        payload_sha256=digest(data),prompt_sha256=digest(prompt(role)),status='submitting',started_at=datetime.now(timezone.utc).isoformat())
    write(path,record)
    def submitted(job_id):record.update(job_id=job_id,status='submitted');write(path,record)
    config=Settings.from_env(provider='router',env_file=ROOT/'.env.router').model_copy(update={'model':model,'mode':'live','max_tokens':8192})
    try:
        answer=RouterClient(config,on_submit=submitted).complete(prompt(role),data,ROLES[role])
        record['completion']=answer.as_dict();core.validate_output(answer.result,state);record['status']='ok'
    except LLMError as e:record.update(status='error',error=str(e))
    record['finished_at']=datetime.now(timezone.utc).isoformat();write(path,record)
    print(path.name,record['status'],flush=True)


def summarize():
    labels={r['case_id']:r['statuses'] for r in json.loads((ROOT/'data/therapy-expansion/expectations.json').read_text())['snapshots']}
    rows=[json.loads(p.read_text()) for p in OUT.glob('*--*.json')];groups=[]
    for model in MODELS:
        group=[r for r in rows if r['model']==model];correct=0;exact=0;plans=0;errors=[]
        ok=[r for r in group if r['status']=='ok'];audits=[r for r in ok if r['role']=='audit']
        for r in audits:
            expected=labels[r['case_id']];actual={x['rule_id']:x['status'] for x in r['completion']['result']['checks']}
            correct+=sum(actual[k]==v for k,v in expected.items());exact+=actual==expected
            for k,v in expected.items():
                if actual[k]!=v:errors.append(dict(case_id=r['case_id'],role='audit',rule_id=k,expected=v,actual=actual[k]))
        for r in [r for r in ok if r['role']=='recommend']:
            mapping={'unknown':'review_record','attention':'request_clinician_review','pending':'schedule_review'}
            expected={k:mapping[v] for k,v in labels[r['case_id']].items() if v in mapping}
            actual={x['rule_id']:x['action'] for x in r['completion']['result']['recommendations']}
            plans+=actual==expected
            if actual!=expected:errors.append(dict(case_id=r['case_id'],role='recommend',expected=expected,actual=actual))
        groups.append(dict(model=model,attempted=len(group),valid=len(ok),planned_jobs=10,valid_audits=len(audits),correct_checks=correct,
            scored_checks=len(audits)*17,planned_checks=85,exact_audits=exact,exact_plans=plans,
            valid_plans=sum(r['role']=='recommend' for r in ok),errors=errors,
            technical_errors=[dict(case_id=r['case_id'],role=r['role'],error=r.get('error'),status=r['status']) for r in group if r['status']!='ok'],
            latency_median_ms=statistics.median(r['completion']['latency_ms'] for r in ok) if ok else None,
            validated_tokens=sum(r['completion']['usage'].get('total',0) for r in ok)))
    result=dict(max_jobs=20,attempted=len(rows),clinical_validation=False,design='Small engineering pilot: 5 author-labelled snapshots, one per profile, no significance or clinical-accuracy claim.',groups=groups)
    write(OUT/'summary.json',result);print(json.dumps(result,ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');parser.add_argument('--summarize',action='store_true');args=parser.parse_args()
    OUT.mkdir(exist_ok=True,parents=True)
    if args.summarize:summarize();return
    cases=[c for c in core.cases() if c.id in CASE_IDS]
    manifest=dict(version=core.VERSION,max_jobs=20,per_model=10,fallback=False,retries=0,concurrency=2,
      cases_sha256=digest([c.model_dump(mode='json') for c in cases]),catalog_sha256=digest(core.registry()),
      expectations_sha256=digest(json.loads((ROOT/'data/therapy-expansion/expectations.json').read_text())),
      prompts={r:prompt(r) for r in ROLES},case_ids=list(CASE_IDS),models=list(MODELS),max_output_tokens=8192,
      role_independence='Identical visible snapshot and contracts; no draft plan, oracle labels or future records shared.')
    path=OUT/'manifest.json'
    if path.exists() and json.loads(path.read_text())!=manifest:raise SystemExit('Frozen inputs changed; use a new experiment.')
    write(path,manifest)
    print('Budget 20 jobs, 10/model, GLM 0, no retries',flush=True)
    if args.live:
        config=Settings.from_env(provider='router',env_file=ROOT/'.env.router')
        with httpx.Client(timeout=30,headers={'Authorization':'Bearer '+config.api_key.get_secret_value()}) as client:
            response=client.get(config.base_url+'/api/v1/models');response.raise_for_status()
            available={m['id']:m for m in response.json()['models']}
        quota={m:{k:available[m][k] for k in ('tier','rpd_limit','used_today','in_flight')} for m in MODELS}
        if any(q['tier']!='free' or q['rpd_limit']-q['used_today']-q['in_flight']<10 for q in quota.values()):raise SystemExit('Insufficient free quota; no jobs sent.')
        write(OUT/'quota-before.json',quota)
        tasks=[(m,c,r) for c in cases for m in MODELS for r in ROLES]
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(run,tasks))
        summarize()


if __name__=='__main__':main()
