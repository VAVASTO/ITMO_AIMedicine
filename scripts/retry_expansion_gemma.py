"""Explicit Gemma repeat with frozen inputs, 4096 tokens and no automatic retries."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys
import threading

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from itmo_aimedicine.config import ROOT, Settings
from itmo_aimedicine import therapy_expansion as core
from itmo_aimedicine.llm import LLMError
from itmo_aimedicine.router import RouterClient, response_schema

BASE = ROOT / 'reports/therapy-expansion'
OUT = ROOT / 'reports/therapy-expansion-gemma-4096'
MODEL = 'gemma-4-31b-it'
ROLES = {'audit': core.ModelAudit, 'recommend': core.ModelPlan}
STOP = threading.Event()
ARRAY_BOUNDS = True


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def write(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def original(case_id, role):
    row = json.loads((BASE / f'{MODEL}--{case_id}--{role}.json').read_text())
    assert digest(row['payload']) == row['payload_sha256'], 'Frozen payload changed'
    return row


class CapturingRouter(RouterClient):
    def __init__(self, settings, record, path, **kwargs):
        super().__init__(settings, **kwargs)
        self.record, self.path = record, path

    def _request(self, client, method, path, **kwargs):
        if method == 'POST':
            self.record['request'] = kwargs['json']
            write(self.path, self.record)
        value = super()._request(client, method, path, **kwargs)
        if method == 'GET' and value.get('status') not in ('queued', 'running'):
            # API response contains only the synthetic task; never persist request headers.
            self.record['router_result'] = value
            write(self.path, self.record)
        return value


def run(task, prompts):
    case_id, role = task
    path = OUT / f'{MODEL}--{case_id}--{role}.json'
    if path.exists():
        return json.loads(path.read_text())
    if STOP.is_set():
        return None
    source = original(case_id, role)
    record = {k: source[k] for k in ('model', 'case_id', 'role', 'review_at', 'payload', 'payload_sha256', 'prompt_sha256')}
    assert digest(prompts[role]) == record['prompt_sha256'], 'Frozen prompt changed'
    record.update(status='submitting', started_at=datetime.now(timezone.utc).isoformat(),
                  original_attempt=str((BASE / path.name).relative_to(ROOT)), max_output_tokens=4096,
                  provider_array_bounds=ARRAY_BOUNDS)
    write(path, record)

    def submitted(job_id):
        record.update(job_id=job_id, status='submitted')
        write(path, record)
        print(case_id, role, 'submitted', flush=True)

    config = Settings.from_env(provider='router', env_file=ROOT / '.env.router').model_copy(
        update={'model': MODEL, 'mode': 'live', 'max_tokens': 4096})
    try:
        answer = CapturingRouter(config, record, path, on_submit=submitted,
                                 schema_array_bounds=ARRAY_BOUNDS).complete(
            prompts[role], record['payload'], ROLES[role])
        record['completion'] = answer.as_dict()
        core.validate_output(answer.result, record['payload']['state'])
        record['status'] = 'ok'
    except LLMError as error:
        record.update(status='error', error=str(error).replace(config.api_key.get_secret_value(), '[redacted]'))
        if record.get('router_result', {}).get('status') in ('failed', 'blocked') or not record.get('router_result'):
            STOP.set()
    record['finished_at'] = datetime.now(timezone.utc).isoformat()
    write(path, record)
    diagnostic = record.get('router_result', {}).get('error', {})
    print(case_id, role, record['status'], str(diagnostic)[:100], flush=True)
    return record


def summarize():
    labels = {r['case_id']: r['statuses'] for r in json.loads(
        (ROOT / 'data/therapy-expansion/expectations.json').read_text())['snapshots']}
    rows = [json.loads(p.read_text()) for p in OUT.glob('*--*.json')]
    ok = [r for r in rows if r['status'] == 'ok']
    audits = [r for r in ok if r['role'] == 'audit']
    plans = [r for r in ok if r['role'] == 'recommend']
    correct = exact = exact_plans = 0
    errors = []
    for row in audits:
        expected = labels[row['case_id']]
        actual = {r['rule_id']: r['status'] for r in row['completion']['result']['checks']}
        correct += sum(actual[k] == v for k, v in expected.items())
        exact += actual == expected
        for key, value in expected.items():
            if actual[key] != value:
                errors.append(dict(case_id=row['case_id'], role='audit', rule_id=key, expected=value, actual=actual[key]))
    mapping = {'unknown': 'review_record', 'attention': 'request_clinician_review', 'pending': 'schedule_review'}
    for row in plans:
        expected = {k: mapping[v] for k, v in labels[row['case_id']].items() if v in mapping}
        actual = {r['rule_id']: r['action'] for r in row['completion']['result']['recommendations']}
        exact_plans += expected == actual
        if expected != actual:
            errors.append(dict(case_id=row['case_id'], role='recommend', expected=expected, actual=actual))
    group = dict(model=MODEL, attempted=len(rows), valid=len(ok), planned_jobs=10,
                 transport_done=sum(r.get('router_result', {}).get('status') == 'done' for r in rows),
                 valid_audits=len(audits), correct_checks=correct, scored_checks=len(audits)*17,
                 planned_checks=85, exact_audits=exact, exact_plans=exact_plans, valid_plans=len(plans),
                 errors=errors, technical_errors=[{k: r.get(k) for k in ('case_id', 'role', 'status', 'error')}
                                                for r in rows if r['status'] != 'ok' and r.get('router_result', {}).get('status') != 'done'],
                 validation_errors=[{k: r.get(k) for k in ('case_id', 'role', 'status', 'error')}
                                    for r in rows if r['status'] != 'ok' and r.get('router_result', {}).get('status') == 'done'],
                 latency_median_ms=statistics.median(r['completion']['latency_ms'] for r in ok) if ok else None,
                 validated_tokens=sum(r['completion']['usage'].get('total', 0) for r in ok))
    result = dict(max_jobs=10, attempted=len(rows), clinical_validation=False, groups=[group],
                  original_experiment='reports/therapy-expansion', max_output_tokens=4096,
                  provider_array_bounds=ARRAY_BOUNDS,
                  comparability='Same frozen inputs and strict local scoring; Gemini original used 8192 tokens, bounded provider arrays and ran earlier.')
    write(OUT / 'summary.json', result)
    print(json.dumps({k: group[k] for k in ('attempted', 'valid', 'correct_checks', 'scored_checks', 'exact_plans', 'valid_plans')}), flush=True)


def main():
    global OUT, ARRAY_BOUNDS
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--summarize', action='store_true')
    parser.add_argument('--compatible', action='store_true', help='Remove provider array bounds; keep strict local validation.')
    args = parser.parse_args()
    if args.compatible:
        OUT = ROOT / 'reports/therapy-expansion-gemma-compatible'
        ARRAY_BOUNDS = False
    OUT.mkdir(parents=True, exist_ok=True)
    if args.summarize:
        summarize()
        return
    base = json.loads((BASE / 'manifest.json').read_text())
    tasks = [(case, role) for case in base['case_ids'] for role in ROLES]
    manifest = dict(model=MODEL, max_jobs=10, max_output_tokens=4096, concurrency=2, fallback=False,
                    automatic_retries=0, original_manifest_sha256=digest(base), prompts=base['prompts'],
                    inputs={f'{case}--{role}': original(case, role)['payload_sha256'] for case, role in tasks},
                    schemas={role: schema.model_json_schema() for role, schema in ROLES.items()},
                    expectations_sha256=base['expectations_sha256'],
                    stop_condition='Stop on the first technical failure; at most one concurrent job may already be running.')
    if args.compatible:
        manifest['provider_array_bounds'] = False
        manifest['local_validation'] = 'Unchanged: 17 ordered unique checks, enum values, event and source citations.'
    assert digest(json.loads((ROOT / 'data/therapy-expansion/expectations.json').read_text())) == manifest['expectations_sha256']
    path = OUT / 'manifest.json'
    if path.exists() and json.loads(path.read_text()) != manifest:
        raise SystemExit('Frozen repeat changed; use a new experiment.')
    write(path, manifest)
    # Reuse the explicitly logged successful diagnostic as the first series item.
    # This avoids paying for the exact same input/configuration a second time.
    probe_path = ROOT / 'reports/therapy-expansion-gemma-diagnostics/full-input-unbounded-arrays.json'
    target = OUT / f'{MODEL}--M01-gap--audit.json'
    if args.compatible and probe_path.exists() and not target.exists():
        probe_record = json.loads(probe_path.read_text())
        if probe_record['status'] == 'ok':
            source = original('M01-gap', 'audit')
            assert probe_record['payload_sha256'] == source['payload_sha256'] == digest(probe_record['payload'])
            assert probe_record['prompt_sha256'] == digest(base['prompts']['audit'])
            config = probe_record['request']['config']
            assert config['maxOutputTokens'] == 4096
            assert config['responseSchema'] == response_schema(core.ModelAudit.model_json_schema(), array_bounds=False)
            core.validate_output(core.ModelAudit.model_validate(probe_record['completion']['result']), probe_record['payload']['state'])
            probe_record.update(adopted_from=str(probe_path.relative_to(ROOT)), provider_array_bounds=False)
            write(target, probe_record)
    if not (args.probe or args.live):
        print('Protocol frozen; no requests sent.')
        return
    config = Settings.from_env(provider='router', env_file=ROOT / '.env.router')
    with httpx.Client(timeout=30, headers={'Authorization': 'Bearer ' + config.api_key.get_secret_value()}) as client:
        response = client.get(config.base_url + '/api/v1/models')
        if response.status_code != 200:
            raise SystemExit('Model catalog HTTP ' + str(response.status_code))
        entry = next(m for m in response.json()['models'] if m['id'] == MODEL)
    remaining = sum(not (OUT / f'{MODEL}--{c}--{r}.json').exists() for c, r in (tasks[:1] if args.probe else tasks))
    if entry['tier'] != 'free' or entry['rpd_limit'] - entry['used_today'] - entry['in_flight'] < remaining:
        raise SystemExit('Insufficient free quota; no submission.')
    write(OUT / ('quota-before-probe.json' if args.probe else 'quota-before-series.json'),
          {k: entry[k] for k in ('tier', 'rpd_limit', 'used_today', 'in_flight')})
    probe = run(tasks[0], base['prompts'])
    if args.live and probe and probe['status'] == 'ok':
        existing = [json.loads(p.read_text()) for p in OUT.glob('*--*.json')]
        if any(r.get('router_result', {}).get('status') in ('failed', 'blocked') or
               r['status'] in ('submitting', 'submitted') for r in existing):
            raise SystemExit('Existing technical failure or pending job; inspect before continuing.')
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda task: run(task, base['prompts']), tasks[1:]))
    summarize()


if __name__ == '__main__':
    main()
