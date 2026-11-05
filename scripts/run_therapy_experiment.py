"""Frozen 56-job budget, resumable role journals, no automatic re-submissions."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from itmo_aimedicine.config import ROOT, Settings
from itmo_aimedicine.llm import LLMError
from itmo_aimedicine.longitudinal import (Audit, Plan, VERSION, cards, cases, formal_checks,
    allowed_action, prompts, snapshot, validate_links)
from itmo_aimedicine.router import RouterClient

OUT = ROOT / 'reports/therapy'
MODELS = ('gemini-3.5-flash-lite', 'gemma-4-31b-it')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def write(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


def run_one(task):
    model, case, review_at, checkpoint = task
    state, knowledge = snapshot(case, review_at), cards()
    prefix = f'{model}--{case.id}--{checkpoint}'
    config = Settings.from_env(provider='router', env_file=ROOT / '.env.router').model_copy(
        update={'model': model, 'mode': 'live', 'max_tokens': 4096})
    outputs = {}
    for role, schema in [('recommend', Plan), ('audit', Audit)]:
        path = OUT / f'{prefix}--{role}.json'
        if path.exists():
            record = json.loads(path.read_text())
            if record['status'] != 'ok':
                print(prefix, role, 'already attempted; not resubmitted', flush=True)
                return
            outputs[role] = schema.model_validate(record['completion']['result'])
            continue
        payload = {'state': state, 'source_cards': knowledge}
        if role == 'audit':
            payload['draft_plan'] = outputs['recommend'].model_dump()
        record = {'case_id': case.id, 'review_at': review_at.isoformat(), 'checkpoint': checkpoint,
                  'model': model, 'role': role, 'version': VERSION, 'status': 'submitting',
                  'started_at': datetime.now(timezone.utc).isoformat(), 'payload': payload,
                  'prompt_sha256': digest(prompts(role)), 'payload_sha256': digest(payload)}
        write(path, record)  # A crash from here must never silently duplicate a POST.
        def submitted(job_id):
            record.update(job_id=job_id, status='submitted')
            write(path, record)
        try:
            completion = RouterClient(config, on_submit=submitted).complete(prompts(role), payload, schema)
            record['completion'] = completion.as_dict()
            validate_links(completion.result, state, knowledge)
            outputs[role] = completion.result
            record['status'] = 'ok'
        except LLMError as error:
            record.update(status='error', error=str(error))
        record['finished_at'] = datetime.now(timezone.utc).isoformat()
        write(path, record)
        print(prefix, role, record['status'], flush=True)
        if record['status'] != 'ok':
            return


def summarize():
    expected = json.loads((ROOT / 'data/therapy/expectations.json').read_text())['snapshots']
    labels = {(e['case_id'], e['review_at']): e['statuses'] for e in expected}
    records = [json.loads(p.read_text()) for p in OUT.glob('*--*.json')]
    result = {'version': VERSION, 'cases': 12, 'snapshots_per_model': len(expected),
              'max_jobs': 4*len(expected), 'models': {}, 'clinical_validation': False}
    for model in MODELS:
        rows = [r for r in records if r['model'] == model]
        successful = [r for r in rows if r['status'] == 'ok']
        audits = [r for r in successful if r['role'] == 'audit']
        details, correct, total, exact = [], 0, 0, 0
        for r in audits:
            target = labels[(r['case_id'], r['review_at'])]
            checks = r['completion']['result']['checks']
            matches = sum(c['status'] == target[c['rule_id']] for c in checks)
            correct += matches; total += len(checks); exact += matches == 4
            details.append({'case_id': r['case_id'], 'review_at': r['review_at'], 'matches': matches,
                            'errors': [{'rule': c['rule_id'], 'expected': target[c['rule_id']], 'actual': c['status']}
                                       for c in checks if c['status'] != target[c['rule_id']]]})
        plans = [r for r in successful if r['role'] == 'recommend']
        plan_exact = 0; plan_details = []
        for r in plans:
            state = r['payload']['state']
            target = {c.rule_id: allowed_action(c, state) for c in formal_checks(state).checks}
            target = {k:v for k,v in target.items() if v}
            actual = {c['rule_id']:c['action'] for c in r['completion']['result']['recommendations']}
            plan_exact += target == actual
            if target != actual:
                plan_details.append({'case_id':r['case_id'],'review_at':r['review_at'],'expected':target,'actual':actual})
        latencies = sorted(r['completion']['latency_ms'] for r in successful)
        n = len(latencies)
        result['models'][model] = {'attempted_jobs':len(rows),'validated_jobs':len(successful),
            'audit_correct_checks':correct,'audit_total_checks':total,'audit_exact_snapshots':exact,
            'audit_snapshots':len(audits),'plan_exact_snapshots':plan_exact,'plan_snapshots':len(plans),
            'audit_details':details,'plan_errors':plan_details,
            'latency_median_ms': (latencies[(n-1)//2]+latencies[n//2])/2 if n else None,
            'tokens':sum(r.get('completion',{}).get('usage',{}).get('total',0) for r in rows),
            'errors':[{'case_id':r['case_id'],'role':r['role'],'status':r['status'],'error':r.get('error')} for r in rows if r['status']!='ok']}
    write(OUT / 'summary.json', result)
    print(json.dumps({m:{k:v for k,v in d.items() if k not in ('audit_details','plan_errors')} for m,d in result['models'].items()}, ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', help='Authorize up to 56 Router jobs, no retries')
    parser.add_argument('--summarize', action='store_true')
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    if args.summarize:
        summarize(); return
    tasks=[(m,c,t,i) for m in MODELS for c in cases() for i,t in enumerate(c.review_times)]
    manifest={'version':VERSION,'models':MODELS,'snapshots_per_model':len(tasks)//2,'max_jobs':len(tasks)*2,
        'cases_sha256':digest([c.model_dump(mode='json') for c in cases()]),'cards_sha256':digest(cards()),
        'expectations_sha256':hashlib.sha256((ROOT/'data/therapy/expectations.json').read_bytes()).hexdigest(),
        'prompts':{r:prompts(r) for r in ('recommend','audit')},'fallback':False,'concurrency':2,'retries':0}
    assert manifest['max_jobs']==56
    path=OUT/'manifest.json'
    if path.exists() and json.loads(path.read_text()) != json.loads(json.dumps(manifest)):
        raise SystemExit('Frozen manifest differs; do not mix experiments.')
    write(path,manifest)
    print('Frozen budget:',manifest['max_jobs'],'jobs;',len(tasks)//2,'snapshots/model',flush=True)
    if args.live:
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(run_one,tasks))
        summarize()


if __name__=='__main__': main()
