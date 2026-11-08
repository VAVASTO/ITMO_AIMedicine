"""Offline multi-profile demo. Model results are read from fixed experiments."""
from datetime import datetime
import json
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import AwareDatetime, Field
from . import therapy_expansion as core
from .config import ROOT
from .longitudinal import StrictModel

router=APIRouter(prefix='/api/multi')


def all_cases():
    path=ROOT/'data/therapy-expansion/synthea-cases.json'
    return core.cases()+([core.Encounter.model_validate(c) for c in json.loads(path.read_text())] if path.exists() else [])


@router.get('/catalog')
def catalog():
    manifest=ROOT/'research/therapy-expansion/synthea-manifest.json'
    return {**core.registry(),'cases':[c.model_dump(mode='json') for c in all_cases()],
            'synthea':json.loads(manifest.read_text()) if manifest.exists() else None,
            'live_enabled':False}


class Evaluation(StrictModel):
    case_id:str=Field(max_length=100)
    review_at:AwareDatetime
    assume_therapy:bool=False
    additions:list[core.Event]=Field(default_factory=list,max_length=10)


@router.post('/evaluate')
def evaluate(body:Evaluation):
    case=next((c for c in all_cases() if c.id==body.case_id),None)
    if case is None or body.review_at not in case.review_times:
        raise HTTPException(422,'Выберите подготовленную историю и момент проверки.')
    ids={e.id for e in case.events}
    if any(e.id in ids or e.occurred_at>body.review_at or e.available_at>body.review_at for e in body.additions):
        raise HTTPException(422,'Новые записи должны иметь уникальные ID и быть доступны к выбранному моменту.')
    if len({e.id for e in body.additions})!=len(body.additions):
        raise HTTPException(422,'Повтор ID новой записи.')
    if body.assume_therapy and case.provenance.get('type')!='synthea':
        raise HTTPException(422,'Допущение отделения применимо только к импорту Synthea.')
    assumption='Учебное допущение: считаем случай терапевтическим. Исходные данные этого не подтверждают.' if body.assume_therapy else None
    if body.assume_therapy:case=case.model_copy(update={'ward':'therapy'})
    before=core.snapshot(case,body.review_at);baseline=core.check(before)
    modified=core.Encounter.model_validate({**case.model_dump(),'events':[*case.events,*body.additions]})
    state=core.snapshot(modified,body.review_at);result=core.check(state)
    old={r['rule_id']:r['status'] for r in baseline['checks']}
    changes=[dict(rule_id=r['rule_id'],before=old[r['rule_id']],after=r['status']) for r in result['checks'] if old[r['rule_id']]!=r['status']]
    recorded=[]
    if not body.additions and not body.assume_therapy:
        experiments=[('gemini-3.5-flash-lite','therapy-expansion','Исходная серия',8192),
                     ('gemma-4-31b-it','therapy-expansion-gemma-compatible','Повтор после исправления формата запроса',4096),
                     ('gemma-4-31b-it','therapy-expansion','Исходная серия: ошибки сохранены',8192)]
        for model,series,label,limit in experiments:
            roles={}
            for role in ('audit','recommend'):
                p=ROOT/'reports'/series/f'{model}--{case.id}--{role}.json'
                if p.exists():
                    record=json.loads(p.read_text())
                    if datetime.fromisoformat(record['review_at'])==body.review_at:
                        roles[role]={'status':record['status'],'completion':record.get('completion'),'error':record.get('error')}
            if roles:
                mapping={'unknown':'review_record','attention':'request_clinician_review','pending':'schedule_review'}
                expected={r['rule_id']:mapping[r['status']] for r in result['checks'] if r['status'] in mapping}
                plan=roles.get('recommend',{})
                actual={r['rule_id']:r['action'] for r in plan.get('completion',{}).get('result',{}).get('recommendations',[])} if plan.get('status')=='ok' and plan.get('completion') else None
                comparison=None if actual is None else {'missing':[k for k in expected if k not in actual],
                    'extra':[k for k in actual if k not in expected],
                    'wrong_action':[k for k in expected if k in actual and actual[k]!=expected[k]]}
                recorded.append(dict(model=model,series_id=series,series_label=label,max_output_tokens=limit,
                                     roles=roles,plan_comparison=comparison))
    return {'snapshot':state,'result':result,'changes':changes,'assumption':assumption,'recorded':recorded,
            'simulation_note':'Добавление записи меняет доступные сведения; клинический исход не моделируется.'}


class Search(StrictModel):
    query:str=Field(min_length=2,max_length=200)
    source_id:str=Field(max_length=40,default='all')


@router.post('/search')
def search(body:Search):
    from .expansion_search import search as query
    try:return {'results':query(body.query,body.source_id)}
    except FileNotFoundError:
        raise HTTPException(503,'Полные тексты доступны в локальном исследовательском индексе. В демо открывайте ссылки на источники.') from None
    except ValueError:
        raise HTTPException(422,'Неизвестный источник.') from None
