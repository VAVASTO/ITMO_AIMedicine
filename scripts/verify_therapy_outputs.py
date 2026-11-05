"""Recheck provenance and saved outputs without contacting any model."""
from collections import Counter
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from itmo_aimedicine.config import ROOT
from itmo_aimedicine.longitudinal import Plan, Audit, cards, validate_links
from itmo_aimedicine.therapy_v2 import temporal_facts
from run_therapy_experiment import digest

groups={}; jobs=[]
for directory in ('therapy','therapy-revision'):
    folder=ROOT/'reports'/directory
    manifest=json.loads((folder/'manifest.json').read_text())
    counts=Counter()
    for path in folder.glob('*--*.json'):
        row=json.loads(path.read_text());counts[row['status']]+=1
        assert row['payload_sha256']==digest(row['payload']),path.name
        prompt=manifest['prompts'][row['condition']][row['role']] if directory=='therapy-revision' else manifest['prompts'][row['role']]
        assert row['prompt_sha256']==digest(prompt),path.name
        assert row['payload']['source_cards']==cards(),path.name
        if row.get('job_id'):jobs.append(row['job_id'])
        if row.get('condition')=='v2':
            assert row['payload']['temporal_facts']==temporal_facts(row['payload']['state']),path.name
            assert 'draft_plan' not in row['payload']
        if row['status']=='ok':
            result=(Plan if row['role']=='recommend' else Audit).model_validate(row['completion']['result'])
            validate_links(result,row['payload']['state'],cards())
            assert row['completion']['model']==row['model'],path.name
            assert row['completion']['job_id']==row['job_id'],path.name
        assert 'statuses' not in row['payload'] and 'expectations' not in row['payload']
    groups[directory]=dict(counts)
    assert sum(counts.values())<=manifest['max_jobs']
assert len(jobs)==len(set(jobs)),'Duplicate submitted job IDs'
output={'groups':groups,'unique_job_ids':len(jobs),'input_hashes_and_links':True,
        'v2_temporal_facts_recomputed':True,'v2_audit_has_no_draft_plan':True,
        'api_calls':0,'all_finished':all(not any(g.get(s,0) for s in ('submitting','submitted')) for g in groups.values())}
(ROOT/'reports/checks/therapy-artifacts.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(output,ensure_ascii=False))
