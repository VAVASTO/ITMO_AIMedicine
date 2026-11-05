"""Paired v1/v2 comparison on eight NEW fixed snapshots, at most 64 submissions."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from itmo_aimedicine.config import ROOT, Settings
from itmo_aimedicine.llm import LLMError
from itmo_aimedicine.longitudinal import Case, Audit, Plan, cards, snapshot, prompts, validate_links
from itmo_aimedicine import therapy_v2
from itmo_aimedicine.router import RouterClient
from run_therapy_experiment import digest, write, MODELS

OUT = ROOT / 'reports/therapy-revision'


def run_one(task):
    model, case, condition = task
    state = snapshot(case, case.review_times[0])
    config = Settings.from_env(provider='router', env_file=ROOT/'.env.router').model_copy(
        update={'model':model, 'mode':'live', 'max_tokens':4096})
    previous = None
    for role, schema in [('recommend', Plan), ('audit', Audit)]:
        path = OUT/f'{model}--{case.id}--{condition}--{role}.json'
        if path.exists():
            existing = json.loads(path.read_text())
            if existing['status'] != 'ok':
                print(path.name, 'already attempted; no resubmission', flush=True)
                if condition == 'v2' and role == 'recommend':
                    # V2 audit does not depend on a successful plan. A resumed
                    # run may fill this unsubmitted slot without retrying the plan.
                    continue
                return
            previous = existing['completion']['result']
            continue
        data = therapy_v2.payload(state) if condition == 'v2' else {'state':state, 'source_cards':cards()}
        prompt = therapy_v2.prompts(role) if condition == 'v2' else prompts(role)
        if condition == 'v1' and role == 'audit':
            data['draft_plan'] = previous
        record = {'model':model, 'case_id':case.id, 'condition':condition, 'role':role,
                  'review_at':state['review_at'], 'payload':data, 'payload_sha256':digest(data),
                  'prompt_sha256':digest(prompt), 'status':'submitting',
                  'started_at':datetime.now(timezone.utc).isoformat()}
        write(path, record)
        def submitted(job_id):
            record.update(job_id=job_id, status='submitted'); write(path, record)
        try:
            completion = RouterClient(config, on_submit=submitted).complete(prompt, data, schema)
            record['completion'] = completion.as_dict()
            validate_links(completion.result, state, cards())
            previous = completion.result.model_dump()
            record['status'] = 'ok'
        except LLMError as error:
            record.update(status='error', error=str(error))
        record['finished_at'] = datetime.now(timezone.utc).isoformat()
        write(path, record)
        print(path.name, record['status'], flush=True)
        if record['status'] != 'ok' and not (condition=='v2' and role=='recommend'): return


def summarize():
    labels = {x['case_id']:x for x in json.loads((ROOT/'data/therapy/revision-expectations.json').read_text())['snapshots']}
    records = [json.loads(p.read_text()) for p in OUT.glob('*--*.json')]
    diagnostics = {r['id']:r for p in (OUT/'diagnostics').glob('*.json') if (r:=json.loads(p.read_text())).get('id')}
    groups = []
    for model in MODELS:
        for condition in ('v1', 'v2'):
            rows = [r for r in records if r['model']==model and r['condition']==condition]
            ok = [r for r in rows if r['status']=='ok']
            audits = [r for r in ok if r['role']=='audit']
            plans = [r for r in ok if r['role']=='recommend']
            errors = []
            correct = exact = plan_exact = 0
            for r in audits:
                actual = {c['rule_id']:c['status'] for c in r['completion']['result']['checks']}
                expected = labels[r['case_id']]['statuses']
                correct += sum(actual[k]==v for k,v in expected.items())
                exact += actual == expected
                if actual != expected: errors.append({'case_id':r['case_id'],'role':'audit','expected':expected,'actual':actual})
            for r in plans:
                actual = {c['rule_id']:c['action'] for c in r['completion']['result']['recommendations']}
                expected = labels[r['case_id']]['actions']
                plan_exact += actual == expected
                if actual != expected: errors.append({'case_id':r['case_id'],'role':'recommend','expected':expected,'actual':actual})
            times = sorted(r['completion']['latency_ms'] for r in ok); n = len(times)
            groups.append({'model':model,'condition':condition,'attempted':len(rows),'valid':len(ok),
                'audit_checks':correct,'audit_total':4*len(audits),'audit_exact':exact,'audit_snapshots':len(audits),
                'plan_exact':plan_exact,'plan_snapshots':len(plans),'errors':errors,
                'latency_median_ms':(times[(n-1)//2]+times[n//2])/2 if n else None,
                'validated_tokens':sum(r['completion'].get('usage',{}).get('total',0) for r in ok),
                'known_total_tokens':sum(r.get('completion',{}).get('usage',diagnostics.get(r.get('job_id'),{}).get('result',{}).get('usage',{})).get('total',0) for r in rows),
                'planned_audit_checks':32,'planned_plan_snapshots':8,
                'missing_audit_snapshots':8-len(audits),'missing_plan_snapshots':8-len(plans),
                'technical_errors':[{'case_id':r['case_id'],'role':r['role'],'status':r['status'],'error':r.get('error')} for r in rows if r['status']!='ok']})
    paired=[]
    for model in MODELS:
        for role in ('audit','recommend'):
            by_condition={v:{r['case_id']:r for r in records if r['model']==model and r['role']==role and r['condition']==v and r['status']=='ok'} for v in ('v1','v2')}
            common=sorted(set(by_condition['v1']) & set(by_condition['v2']))
            scores={}
            for v in ('v1','v2'):
                correct=0
                for cid in common:
                    data=by_condition[v][cid]['completion']['result']
                    if role=='audit':
                        correct+=sum(c['status']==labels[cid]['statuses'][c['rule_id']] for c in data['checks'])
                    else:
                        correct+=({r['rule_id']:r['action'] for r in data['recommendations']}==labels[cid]['actions'])
                scores[v]=correct
            paired.append({'model':model,'role':role,'case_ids':common,'total':len(common)*(4 if role=='audit' else 1),'scores':scores})
    result = {'paired_complete_cases':paired,'max_jobs':64,'attempted':len(records),'snapshots':8,'conditions':['v1','v2'],
        'design':'Paired fixed new cases, alternating condition order. One run per cell, no inference of statistical significance.',
        'intervention':'Computed temporal facts + scoped exception reminder + audit independent of draft plan; combined effect, no ablation.',
        'clinical_validation':False,'groups':groups}
    write(OUT/'summary.json',result)
    print(json.dumps(result,ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--summarize', action='store_true')
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    if args.summarize: summarize(); return
    cases=[Case.model_validate(x) for x in json.loads((ROOT/'data/therapy/revision-cases.json').read_text())]
    manifest={'cases_sha256':digest([c.model_dump(mode='json') for c in cases]),'cards_sha256':digest(cards()),
        'labels_sha256':digest(json.loads((ROOT/'data/therapy/revision-expectations.json').read_text())),
        'prompts':{v:{r:(therapy_v2.prompts(r) if v=='v2' else prompts(r)) for r in ('recommend','audit')} for v in ('v1','v2')},
        'max_jobs':64,'per_model':32,'models':MODELS,'fallback':False,'retries':0,'concurrency':2,
        'design':'v1 then v2 for odd cases, v2 then v1 for even cases; 8 new snapshots'}
    path=OUT/'manifest.json'
    if path.exists() and json.loads(path.read_text()) != json.loads(json.dumps(manifest)):
        raise SystemExit('Frozen manifest differs; use a new experiment directory.')
    write(path,manifest)
    tasks=[(m,c,v) for i,c in enumerate(cases) for v in (('v1','v2') if i%2==0 else ('v2','v1')) for m in MODELS]
    print('Budget: 64 jobs, 32/model, no retries',flush=True)
    if args.live:
        with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(run_one,tasks))
        summarize()


if __name__=='__main__': main()
