import json
import os
from datetime import datetime, timezone
from threading import Lock
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import AwareDatetime, Field

from .config import ROOT, Settings
from .llm import LLMError
from .smoke import run_smoke
from .longitudinal import StrictModel, Case, Plan, Audit, cards, cases, formal_checks, snapshot, run_pipeline as run_v1, consistency, allowed_action
from .therapy_v2 import VERSION, run_pipeline, temporal_facts
from .knowledge_search import search
from .simulation import Simulation, simulate
from .demo_security import demo_guard, live_enabled
from .router import RouterClient

app = FastAPI(title="ITMO AIMedicine: терапевтический сценарий", version="0.2.0")
live_lock = Lock()
app.middleware('http')(demo_guard)


def all_cases():
    revision = ROOT/'data/therapy/revision-cases.json'
    return cases() + ([Case.model_validate(c) for c in json.loads(revision.read_text())] if revision.exists() else [])


def settings():
    try:
        router_config = ROOT / '.env.router'
        return Settings.from_env(env_file=router_config if router_config.exists() else None)
    except ValueError:
        raise HTTPException(503, "Некорректные настройки приложения.") from None


@app.get("/api/status")
def status():
    config = settings()
    return {"provider": config.provider, "model": config.model, "mode": config.mode,
            "key_configured": bool(config.api_key.get_secret_value()),
            "gemini_status": "router_configured" if config.provider == 'router' else "not_selected",
            "stage": "2: сквозной сценарий терапии"}


@app.post("/api/smoke")
def smoke():
    if os.getenv('PUBLIC_DEMO') == '1':
        raise HTTPException(403, 'Технический запуск отключён во внешней демонстрации.')
    try:
        return run_smoke(settings()).as_dict()
    except LLMError as error:
        raise HTTPException(502, str(error)) from None


@app.get('/api/therapy/catalog')
def catalog():
    return {'version': VERSION, 'cases':[c.model_dump(mode='json') for c in all_cases()],
            'cards':cards(), 'models':['gemini-3.5-flash-lite','gemma-4-31b-it'],
            'clinical_validation':False,'live_enabled':live_enabled()}


class SearchQuery(StrictModel):
    query: str = Field(min_length=2,max_length=200)
    scope: Literal['clinical','inpatient','all'] = 'inpatient'


@app.post('/api/therapy/search')
def knowledge_search(body: SearchQuery):
    try:
        return {'results':search(body.query,body.scope),'clinical_validation':False}
    except FileNotFoundError:
        raise HTTPException(503,'Локальный индекс не собран. См. инструкцию по запуску.') from None


@app.post('/api/therapy/simulate')
def simulation(body: Simulation):
    return simulate(body)


class Evaluation(StrictModel):
    case_id: str
    review_at: AwareDatetime
    mode: Literal['formal','recorded','live'] = 'formal'
    model: Literal['gemini-3.5-flash-lite','gemma-4-31b-it'] = 'gemma-4-31b-it'
    condition: Literal['v1','v2'] = 'v2'


@app.post('/api/therapy/evaluate')
def evaluate(body: Evaluation, request: Request):
    # Local demo: protect the key-backed action from a cross-site request.
    origin = request.headers.get('origin')
    if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
        # Vite's documented local dev origin is also allowed.
        if origin not in {'http://127.0.0.1:5173', 'http://localhost:5173'}:
            raise HTTPException(403, 'Недопустимый источник запроса.')
    case = next((c for c in all_cases() if c.id == body.case_id), None)
    if case is None or body.review_at not in case.review_times:
        raise HTTPException(422, 'Выберите подготовленный синтетический случай и точку проверки.')
    state = snapshot(case, body.review_at)
    base = {'version':VERSION,'mode':body.mode,'snapshot':state,
            'formal_reference':formal_checks(state).model_dump(),'clinical_validation':False,
            'temporal_facts':temporal_facts(state),'condition':body.condition}
    formal_actions = [{'rule_id':check.rule_id,'action':allowed_action(check,state),'source_id':check.source_id}
                      for check in formal_checks(state).checks if allowed_action(check,state)]
    base['formal_actions'] = formal_actions
    if body.mode == 'formal':
        return base
    if body.mode == 'recorded':
        checkpoint = case.review_times.index(body.review_at)
        for role, field in [('recommend','plan'),('audit','audit')]:
            if case.id.startswith('V'):
                path = ROOT/'reports/therapy-revision'/f'{body.model}--{case.id}--{body.condition}--{role}.json'
            else:
                if body.condition != 'v1':
                    raise HTTPException(422,'Для T01–T12 сохранена исходная версия. Выберите v1 или случай V01–V08.')
                path = ROOT / 'reports/therapy' / f'{body.model}--{case.id}--{checkpoint}--{role}.json'
            if not path.exists():
                raise HTTPException(404,'Сохранённого ответа для этой точки пока нет.')
            record = json.loads(path.read_text())
            if record['status'] != 'ok':
                raise HTTPException(409,'Сохранённый запуск не прошёл проверку. См. журнал эксперимента.')
            base[field] = record['completion']
        base['consistency'] = consistency(Plan.model_validate(base['plan']['result']),
                                           Audit.model_validate(base['audit']['result']), state)
        return base
    if not live_enabled():
        raise HTTPException(403,'Новые запросы отключены в этой демонстрации. Доступны сохранённые ответы.')
    config = settings()
    if config.provider != 'router' or config.mode != 'live':
        raise HTTPException(503,'Для живого запуска настройте Router в локальном .env.router.')
    if not live_lock.acquire(blocking=False):
        raise HTTPException(409,'Другой запрос уже выполняется. Дождитесь результата.')
    run_id = uuid4().hex
    journal = {'run_id':run_id,'case_id':case.id,'review_at':body.review_at.isoformat(),'jobs':[],'status':'running',
               'condition':body.condition,'started_at':datetime.now(timezone.utc).isoformat()}
    path = ROOT/'reports/live'/f'therapy-ui-{run_id}.json'
    def persist():
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(journal,ensure_ascii=False,indent=2))
    def submitted(job_id):
        journal['jobs'].append(job_id)
        persist()
    try:
        # Reserve two jobs per click, including failed/unfinished clicks. Journals
        # survive restarts; deployment uses one worker and one persistent volume.
        day = journal['started_at'][:10]
        used = sum(2 for p in (ROOT/'reports/live').glob('therapy-ui-*.json')
                   if json.loads(p.read_text()).get('started_at','')[:10] == day)
        try:
            budget = int(os.getenv('DEMO_DAILY_JOB_LIMIT','8'))
        except ValueError:
            raise HTTPException(503,'Некорректный дневной лимит.') from None
        if used + 2 > budget:
            raise HTTPException(429,'Дневной лимит новых запросов приложения исчерпан. Сохранённые ответы доступны.')
        persist()
        pipeline = run_pipeline if body.condition == 'v2' else run_v1
        result = {'mode':'live','condition':body.condition,'formal_actions':formal_actions,**pipeline(case, body.review_at,
            RouterClient(config.model_copy(update={'model':body.model,'max_tokens':4096}),on_submit=submitted,normalize_wrapper=True))}
        journal.update(status='ok',result=result)
        persist()
        return result
    except LLMError as error:
        journal.update(status='error',error=str(error))
        persist()
        raise HTTPException(502,str(error)) from None
    finally:
        live_lock.release()


if (ROOT/'frontend/dist').exists():
    app.mount('/',StaticFiles(directory=ROOT/'frontend/dist',html=True),name='ui')
