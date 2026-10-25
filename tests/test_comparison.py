from copy import deepcopy
import json
from pathlib import Path

import pytest

from itmo_aimedicine.comparison import (
    LIMITS, ComparisonReply, available_documents, evaluate, plan_rows,
    prepare_payload, reserve_attempt, specification,
)


def test_comparison_packet_is_disjoint_from_development_and_labels_stay_out():
    cases,labels=specification()
    old=json.loads(Path('data/research/feature-cases.json').read_text())
    assert not {c['family_id'] for c in cases}&{c['family_id'] for c in old}
    assert len({c['documents'][0]['text'] for c in cases})==12
    for c,e in zip(cases,labels):
        p=prepare_payload(c,e['criterion_id'],False)
        assert set(p)=={'criterion_id','case'}
        assert not {'id','family_id','split','expected_status','purpose'}&set(p['case'])
        assert e['purpose'] not in json.dumps(p,ensure_ascii=False)


def test_filter_removes_all_future_data_without_mutating_input():
    cases,labels=specification()
    for c,e in zip(cases,labels):
        original=deepcopy(c)
        p=prepare_payload(c,e['criterion_id'],True)
        assert c==original
        assert p['case']['documents']==available_documents(c)
        for term in e['forbidden_future_markers']:
            assert term.casefold() not in json.dumps(p,ensure_ascii=False).casefold()


def test_equal_time_included_and_unknown_or_invalid_time_excluded():
    c={'review_at':'2026-10-14T12:00:00+03:00','documents':[
        {'id':'edge','available_at':'2026-10-14T09:00:00+00:00'},
        {'id':'later','available_at':'2026-10-14T12:00:01+03:00'},
        {'id':'missing'}, {'id':'invalid','available_at':'??'},
        {'id':'naive','available_at':'2026-10-14T11:00:00'}]}
    assert [d['id'] for d in available_documents(c)]==['edge']


def test_plan_has_exact_budget_and_balanced_pair_order():
    cases,labels=specification();rows=plan_rows(cases,labels)
    assert {p:sum(r['provider']==p for r in rows) for p in LIMITS}==LIMITS
    for c in cases:
        group=[r for r in rows if r['case']['id']==c['id']]
        assert {r['condition'] for r in group}=={'glm_full','glm_filtered','mistral_filtered'}
        filtered=[prepare_payload(c,r['expected']['criterion_id'],True) for r in group if r['filtered']]
        assert filtered[0]==filtered[1]
    glm=[r for r in rows if r['provider']=='glm']
    assert sum(glm[i]['condition']=='glm_full' for i in range(0,24,2))==6


@pytest.mark.parametrize('provider',['glm','mistral'])
def test_persistent_budget_counts_unfinished_requests_and_refuses_overrun(tmp_path,provider):
    for i in range(LIMITS[provider]):reserve_attempt(tmp_path,provider,str(i),'test')
    with pytest.raises(RuntimeError,match='exhausted'):
        reserve_attempt(tmp_path,provider,'one-more','test')
    assert len(list(tmp_path.glob(f'{provider}-*.json')))==LIMITS[provider]


def test_evaluator_catches_future_explanation_even_when_status_correct():
    cases,labels=specification();c=cases[2];e=labels[2]
    reply=ComparisonReply(criterion_id='C02',status='insufficient_evidence',explanation='Поздний результат описывает 27 мм в S6.',available_document_ids=['admission'],evidence_document_ids=[],evidence_quotes=[],normative_conclusion_allowed=False)
    checks=evaluate(c,e,reply)
    assert checks['status_match'] and checks['references_valid']
    assert not checks['no_flagged_future_markers'] and not checks['all_automatic_checks']


def test_evaluator_rejects_wrong_quotes_and_missing_required_evidence():
    cases,labels=specification();c=cases[0];e=labels[0]
    reply=ComparisonReply(criterion_id='C03',status='confirmed',explanation='Протокол доступен.',available_document_ids=['admission','result'],evidence_document_ids=['result'],evidence_quotes=[{'document_id':'result','quote':'Выдуманный фрагмент'}],normative_conclusion_allowed=False)
    assert not evaluate(c,e,reply)['quotes_valid']
    reply.evidence_quotes[0].quote=c['documents'][1]['text']
    assert evaluate(c,e,reply)['all_automatic_checks']
    reply.evidence_document_ids=[];reply.evidence_quotes=[]
    assert not evaluate(c,e,reply)['required_evidence_present']
