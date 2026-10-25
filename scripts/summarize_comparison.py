"""Export saved trial evidence, without sending requests or rewriting raw responses."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    raw=ROOT/'reports/live/comparison-v1-2026-10-25'
    data=json.loads((raw/'results.json').read_text())
    if 'conditions' not in data or len(data['records'])!=36:
        raise ValueError('The comparison has not finished')
    data['preflight']=json.loads((ROOT/'reports/checks/comparison-preflight-2026-10-25.json').read_text())
    postflight=ROOT/'reports/checks/comparison-postflight-2026-10-25.json'
    if postflight.exists():
        data['postflight']=json.loads(postflight.read_text())
    data['attempts_by_provider']={p:len(list((raw/'reservations').glob(p+'-*.json'))) for p in ('glm','mistral')}
    assert data['attempts_by_provider']['glm']<=24
    assert data['attempts_by_provider']['mistral']<=12
    for condition,summary in data['conditions'].items():
        rows=[r for r in data['records'] if r['condition']==condition and r['state']=='completed']
        summary['check_failures']={key:sum(not r['checks'][key] for r in rows) for key in rows[0]['checks'] if key not in ('flagged_future_markers','all_automatic_checks')} if rows else {}
        times=[r['latency_ms'] for r in rows]
        summary['latency_range_ms']=[min(times),max(times)] if times else None
    # A read-only review sheet hides provider and condition, but is not an independent clinical review.
    order=sorted([r for r in data['records'] if r['state']=='completed'],key=lambda r:hashlib.sha256((r['case_id']+r['condition']).encode()).hexdigest())
    mapping=[];sheet=[]
    for i,row in enumerate(order,1):
        review_id=f'R{i:02d}'
        mapping.append({'review_id':review_id,'case_id':row['case_id'],'condition':row['condition']})
        sheet.append({'review_id':review_id,'case_id':row['case_id'],'result':row['result']})
    data['review_map']=mapping
    out=ROOT/'reports/checks/comparison-2026-10-25.json'
    out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    (raw/'review-without-model-labels.json').write_text(json.dumps(sheet,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'attempts':data['attempts_by_provider'],'conditions':data['conditions']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
