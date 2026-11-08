"""Versioned, research-only checks for five adult therapy profiles.

Clinical source checks and author-defined documentation checks remain distinct.
Missing records never establish that a clinical intervention was omitted.
"""
from datetime import datetime, timedelta
from functools import lru_cache
import json
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from .config import ROOT
from .longitudinal import StrictModel
from .llm import LLMError

VERSION = 'therapy-multi-v3'
Disease = Literal['CAP', 'COPD', 'HTN', 'HF', 'DM2']
Status = Literal['met', 'attention', 'unknown', 'pending', 'not_applicable']
RuleId = Literal['Q01','Q02','Q03','Q04','Q05','Q06','Q07','Q08','Q09',
                 'Q10','Q11','Q12','Q13','Q14','Q15','Q16','Q17']


@lru_cache
def registry():
    return json.loads((ROOT/'research/therapy-expansion/catalog.json').read_text())


class Event(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    kind: Literal['diagnosis','history','allergy_review','observation','lab','procedure',
                  'order','administration','medication_stop','reassessment','treatment_review',
                  'followup_plan','discharge','exception','renal_review']
    code: str = Field(default='', max_length=100)
    value: str = Field(default='', max_length=500)
    occurred_at: AwareDatetime
    available_at: AwareDatetime
    details: dict[str, str] = Field(default_factory=dict, max_length=20)

    @model_validator(mode='after')
    def chronology(self):
        if self.available_at < self.occurred_at:
            raise ValueError('A record cannot be available before its event.')
        if any(len(k)>100 or len(v)>1000 for k,v in self.details.items()):
            raise ValueError('Event detail too long.')
        return self


class Encounter(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    patient_id: str = Field(min_length=1, max_length=100)
    title: str = Field(max_length=200)
    age: int = Field(ge=0, le=120)
    primary: Disease
    comorbidities: list[Disease] = Field(default_factory=list, max_length=5)
    renal_risk: bool = False
    ward: Literal['therapy','icu','other'] = 'therapy'
    admission_at: AwareDatetime
    review_times: list[AwareDatetime] = Field(min_length=1, max_length=20)
    events: list[Event] = Field(max_length=2000)
    provenance: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode='after')
    def unique_events(self):
        if len({e.id for e in self.events}) != len(self.events):
            raise ValueError('Event IDs must be unique within a case.')
        if any(t < self.admission_at for t in self.review_times):
            raise ValueError('Review cannot precede admission.')
        return self


def cases():
    return [Encounter.model_validate(x) for x in json.loads(
        (ROOT/'data/therapy-expansion/cases.json').read_text())]


def snapshot(case: Encounter, at: datetime):
    if at < case.admission_at:
        raise ValueError('Review cannot precede admission.')
    # The title, review schedule, provenance and future labels are not model input.
    return {'case_id':case.id, 'age':case.age, 'primary':case.primary,
            'comorbidities':case.comorbidities, 'renal_risk':case.renal_risk,
            'ward':case.ward, 'admission_at':case.admission_at.isoformat(),
            'review_at':at.isoformat(), 'events':[e.model_dump(mode='json') for e in
                sorted(case.events,key=lambda e:(e.occurred_at,e.id))
                if e.occurred_at<=at and e.available_at<=at]}


def temporal_facts(state):
    events=state['events']; at=datetime.fromisoformat(state['review_at'])
    kinds=lambda k:[e for e in events if e['kind']==k]
    first=lambda k:next(iter(kinds(k)),None)
    def delta(a,b):
        return (datetime.fromisoformat(a)-datetime.fromisoformat(b)).total_seconds()
    diagnosis=next((e for e in kinds('diagnosis') if e['code']==state['primary']),None)
    ab_order=None
    # Compare actual instants, never lexical ISO strings with different offsets.
    if diagnosis:
        ab_order=next((e for e in kinds('order') if e['details'].get('class')=='antibiotic' and
                       delta(e['occurred_at'],diagnosis['occurred_at'])>=0),None)
    start=next((e for e in kinds('administration') if e['details'].get('class')=='antibiotic' and
                (not diagnosis or delta(e['occurred_at'],diagnosis['occurred_at'])>=0)),None)
    discharge=first('discharge')
    return {'stay_seconds':delta(discharge['occurred_at'] if discharge else at.isoformat(),state['admission_at']),
            'antibiotic_order_after_diagnosis_seconds':delta(ab_order['occurred_at'],diagnosis['occurred_at']) if ab_order else None,
            'diagnosis_elapsed_seconds':delta(at.isoformat(),diagnosis['occurred_at']) if diagnosis else None,
            'antibiotic_start_elapsed_seconds':delta(at.isoformat(),start['occurred_at']) if start else None,
            'antibiotic_start_event_id':start['id'] if start else None,
            'reassessment_seconds_from_start':[
                {'event_id':e['id'],'seconds':delta(e['occurred_at'],start['occurred_at'])}
                for e in kinds('reassessment')] if start else [],
            'duration_note':'Stay duration and medication course duration are independent quantities.'}


def check(state):
    """Evaluate explicit records, without diagnosing or selecting medications."""
    reg=registry(); rules=reg['rules']; events=state['events']
    now=datetime.fromisoformat(state['review_at']); admission=datetime.fromisoformat(state['admission_at'])
    t=lambda e:datetime.fromisoformat(e['occurred_at'])
    ev=lambda kind:[e for e in events if e['kind']==kind]
    current=lambda kind:[e for e in ev(kind) if t(e)>=admission]
    out=[]; facts=temporal_facts(state)
    profiles=[reg['profiles'][k] for k in dict.fromkeys([state['primary'],*state['comorbidities']])]
    def result(r,status,why,evidence=()):
        out.append({'rule_id':r['id'],'category':r['category'],'status':status,'explanation':why,
                    'evidence_ids':[e['id'] for e in evidence], 'source_ids':r['sources'],
                    'basis':r['basis'],'clinical_validation':False})
    for r in rules:
        rid=r['id']
        if state['age']<18 or state['ward']!='therapy':
            result(r,'not_applicable','Вне области взрослого терапевтического пилота.');continue
        exclusions=[e for e in current('exception') if e['code']==rid]
        if exclusions:
            result(r,'unknown','Зафиксировано исключение; нужен разбор врачом.',exclusions);continue
        orders=current('order'); starts=current('administration')
        if rid=='Q01':
            found=[e for e in current('diagnosis') if e['code']==state['primary']]
            result(r,'met' if found else 'unknown','Запись основного диагноза найдена.' if found else 'Нет доступной записи основного диагноза.',found)
        elif rid=='Q02':
            found=[e for e in current('history') if e['code']=='medication_reconciliation']
            result(r,'met' if found else 'unknown','Сведения о постоянной терапии сверены.' if found else 'Не записана сверка постоянной терапии.',found)
        elif rid=='Q03':
            found=current('allergy_review')
            valid=[e for e in found if e['value'] in ('none_known','known')]
            if not orders: result(r,'met' if valid else 'unknown','Статус аллергий записан.' if valid else 'Статус аллергий неизвестен.',valid)
            else:
                first=t(orders[0]); before=[e for e in valid if t(e)<=first and datetime.fromisoformat(e['available_at'])<=first]
                result(r,'met' if before else 'attention' if valid else 'unknown',
                       'Аллергоанамнез записан до первого назначения.' if before else 'До первого назначения нет доступной определённой записи об аллергиях.',before or valid)
        elif rid in ('Q04','Q05','Q06'):
            field,kind={'Q04':('observations','observation'),'Q05':('labs','lab'),'Q06':('procedures','procedure')}[rid]
            required={}
            for profile in profiles:
                for code, days in profile[field].items():
                    cutoff=now-timedelta(days=days) if days else admission
                    required[code]=max(required.get(code,cutoff),cutoff)
            found=[e for e in ev(kind) if e['code'] in required and t(e)>=required[e['code']] and e['value'] not in ('','unknown','ordered')]
            missing=sorted(set(required)-{e['code'] for e in found})
            result(r,'unknown' if missing else 'met','Нет доступного результата: '+', '.join(missing) if missing else 'Есть результаты выбранного исследовательского набора.',found)
        elif rid=='Q07':
            bad=[e for e in orders if any(not e['details'].get(k) for k in ('dose','route','frequency'))]
            result(r,'unknown' if not orders or bad else 'met','Нет полных дозы, пути и кратности в записи.' if not orders or bad else 'Поля назначения заполнены; правильность дозы не проверяется.',bad or orders)
        elif rid=='Q08':
            reviews=current('allergy_review');conflicts=[];uncertain=False
            for order in orders:
                prior=[a for a in reviews if t(a)<=t(order) and datetime.fromisoformat(a['available_at'])<=t(order)]
                if not prior or prior[-1]['value'] not in ('known','none_known'): uncertain=True;continue
                allergy=prior[-1]
                codes=set(filter(None,allergy['details'].get('substances','').split(',')))
                if allergy['value']=='known' and not codes:uncertain=True
                if codes & {order['code'],order['details'].get('class','')}:conflicts.extend([allergy,order])
            result(r,'not_applicable' if not orders else 'attention' if conflicts else 'unknown' if uncertain else 'met',
                   'Совпадение с явно записанным аллергеном; требуется врач.' if conflicts else 'Проверено точное совпадение кодов, перекрёстные реакции не моделируются.' if orders and not uncertain else 'Недостаточно данных для проверки назначения.',conflicts)
        elif rid=='Q09':
            found=current('renal_review')
            result(r,'not_applicable' if not state['renal_risk'] or not orders else 'met' if found else 'unknown',
                   'При отмеченном почечном риске проверяется запись врачебного разбора терапии; дозы не рассчитываются.',found)
        elif rid=='Q10':
            diagnoses={e['id']:e for e in current('diagnosis')}
            bad=[e for e in orders if e['details'].get('indication_event_id') not in diagnoses or datetime.fromisoformat(diagnoses[e['details']['indication_event_id']]['available_at'])>t(e)]
            result(r,'not_applicable' if not orders else 'unknown' if bad else 'met',
                   'Назначение связано с записью диагноза; клиническая обоснованность препарата требует врача.',bad or orders)
        elif rid=='Q11':
            if state['primary']!='CAP':result(r,'not_applicable','Интервал 4 ч применяется только к выбранному сценарию ВП.');continue
            interval=facts['antibiotic_order_after_diagnosis_seconds'];elapsed=facts['diagnosis_elapsed_seconds']
            status='unknown' if elapsed is None else ('met' if interval<=14400 else 'attention') if interval is not None else 'pending' if elapsed<=14400 else 'unknown'
            result(r,status,'Назначение антибиотика от диагноза: '+(str(interval/3600)+' ч.' if interval is not None else 'нет данных.'),[e for e in orders if e['details'].get('class')=='antibiotic'])
        elif rid=='Q12':
            invalid=[s for s in starts if not any(o['id']==s['details'].get('order_id') and o['code']==s['code'] and datetime.fromisoformat(o['available_at'])<=t(s) for o in orders)]
            result(r,'not_applicable' if not starts else 'attention' if invalid else 'met','Начало лечения сверено с предшествующим назначением.',invalid or starts)
        elif rid=='Q13':
            if state['primary']!='CAP':result(r,'not_applicable','Окно 48–72 ч в этой версии задано только для ВП.');continue
            elapsed=facts['antibiotic_start_elapsed_seconds'];timed=facts['reassessment_seconds_from_start']
            good={x['event_id'] for x in timed if 172800<=x['seconds']<=259200}
            status='met' if good else 'unknown' if elapsed is None else 'pending' if elapsed<=259200 else 'attention' if any(x['seconds']>259200 for x in timed) else 'unknown'
            result(r,status,'Оценка ответа отсчитывается от фактического начала антибиотика.',[e for e in events if e['id'] in good])
        elif rid=='Q14':
            worse=[e for e in current('reassessment') if e['value']=='worsening']
            reviewed=[e for e in current('treatment_review') if worse and t(e)>=t(worse[-1])]
            result(r,'not_applicable' if not worse else 'met' if reviewed else 'attention','После последнего записанного ухудшения нужен разбор тактики врачом.',worse[-1:]+reviewed)
        elif rid=='Q15':
            plans=[e for e in current('followup_plan') if e['details'].get('due_at')]
            if not plans:result(r,'unknown','Нет записанного срока следующей оценки.');continue
            plan=plans[-1]
            try:due=datetime.fromisoformat(plan['details']['due_at']);assert due.tzinfo
            except (ValueError,AssertionError):result(r,'unknown','Срок следующей оценки не распознан.',[plan]);continue
            done=[e for e in current('reassessment') if t(e)>=t(plan) and t(e)<=due and e['details'].get('plan_id')==plan['id']]
            result(r,'met' if done else 'pending' if now<=due else 'unknown','Проверяется срок, явно заданный врачом, без универсального интервала.',[plan]+done)
        elif rid=='Q16':
            discharged=current('discharge')
            if not discharged:result(r,'not_applicable','Выписка ещё не записана.');continue
            d=discharged[-1];missing=[k for k in ('diagnosis','medication_plan','followup') if not d['details'].get(k)]
            result(r,'unknown' if missing else 'met','Не заполнено: '+', '.join(missing) if missing else 'Выбранные поля выписки заполнены.',[d])
        elif rid=='Q17':
            stops=current('medication_stop');bad=[]
            for stop in stops:
                matches=[s for s in starts if s['id']==stop['details'].get('start_id')]
                if not matches or t(stop)<t(matches[0]):bad.append(stop)
            result(r,'not_applicable' if not stops else 'attention' if bad else 'met','Срок госпитализации и длительность курса считаются отдельно; равенство не требуется.',bad or stops)
    return {'version':VERSION,'checks':out,'temporal_facts':facts,'clinical_validation':False,
            'recommendations':[{'rule_id':c['rule_id'],'action':'review_record','source_ids':c['source_ids'],
                                'reason':c['explanation']} for c in out if c['status'] in ('unknown','attention','pending')]}


class Finding(StrictModel):
    rule_id: RuleId
    status: Status
    explanation: str = Field(max_length=1500)
    evidence_ids: list[str]
    source_ids: list[str]


class ModelAudit(StrictModel):
    checks: list[Finding] = Field(min_length=17,max_length=17)


class Suggestion(StrictModel):
    rule_id: RuleId
    action: Literal['review_record','request_clinician_review','schedule_review']
    explanation: str = Field(max_length=1500)
    evidence_ids: list[str]
    source_ids: list[str]


class ModelPlan(StrictModel):
    recommendations: list[Suggestion] = Field(max_length=17)


PROMPT = '''You examine a synthetic adult inpatient therapy record for research.
Use only visible events and the supplied profile and rule contracts. Never prescribe drugs,
doses, diagnose a patient, or infer unrecorded care. Missing documentation is unknown, not
proof of a violation. Separate clinical-source checks from author-defined workflow checks.
Honor rule-specific exceptions and exact inclusive time bounds. The two roles work independently.
Return schema-valid JSON only, with Russian explanations. Cite only supplied rule source IDs
and actual visible event IDs. Do not include prose outside JSON.'''


def payload(state):
    reg=registry()
    return {'state':state,'temporal_facts':temporal_facts(state),'rules':reg['rules'],
            'global_contract':reg['global_contract'],
            'profiles':{k:reg['profiles'][k] for k in dict.fromkeys([state['primary'],*state['comorbidities']])}}


def validate_output(output,state):
    rows=output.checks if isinstance(output,ModelAudit) else output.recommendations
    ids=[r.rule_id for r in rows];expected=[r['id'] for r in registry()['rules']]
    if len(ids)!=len(set(ids)) or isinstance(output,ModelAudit) and ids!=expected:
        raise LLMError('Повтор или неполный набор правил в ответе модели.')
    visible={e['id'] for e in state['events']};rules={r['id']:r for r in registry()['rules']}
    for row in rows:
        if not set(row.evidence_ids)<=visible or not row.source_ids or not set(row.source_ids)<=set(rules[row.rule_id]['sources']):
            raise LLMError('Неподтверждённые ссылки в ответе модели.')
