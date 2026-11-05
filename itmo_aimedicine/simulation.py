"""Interactive synthetic workflow, not a calibrated disease/therapy model."""
from datetime import datetime, timedelta
from typing import Literal
from pydantic import Field, model_validator

from .longitudinal import StrictModel, Event, Case, snapshot, formal_checks, allowed_action
from .therapy_v2 import temporal_facts

START = datetime.fromisoformat('2026-11-01T08:00:00+03:00')


class PhysicianAction(StrictModel):
    kind: Literal['measure_spo2','antibiotic_order','antibiotic_start','reassessment','treatment_review']
    hour: float = Field(ge=0,le=168,allow_inf_nan=False)


class Simulation(StrictModel):
    elapsed_hours: float = Field(default=0,ge=0,le=168,allow_inf_nan=False)
    response: Literal['improving','unchanged','worsening'] = 'improving'
    actions: list[PhysicianAction] = Field(default_factory=list,max_length=40)

    @model_validator(mode='after')
    def valid_history(self):
        last=-1; order=start=None
        for index,action in enumerate(self.actions):
            if action.hour<last or action.hour>self.elapsed_hours:
                raise ValueError('Actions must be chronological and cannot occur in the future')
            last=action.hour
            if action.kind=='antibiotic_order':
                if order is not None: raise ValueError('This pilot permits one initial order')
                order=action.hour
            if action.kind=='antibiotic_start':
                if order is None: raise ValueError('Document an order before starting therapy')
                if start is not None: raise ValueError('Start is already documented')
                start=action.hour
            if action.kind in {'reassessment','treatment_review'} and start is None:
                raise ValueError('Treatment start is needed for this scenario action')
            if action.kind=='treatment_review' and not any(a.kind=='reassessment' for a in self.actions[:index]):
                raise ValueError('Record an assessment before a treatment review')
        return self


def simulate(body: Simulation):
    events=[Event(id='SIM-diagnosis',kind='diagnosis',occurred_at=START,available_at=START,value='confirmed_cap')]
    for index,action in enumerate(body.actions):
        at=START+timedelta(hours=action.hour)
        kind='spo2' if action.kind=='measure_spo2' else action.kind
        value='95' if kind=='spo2' else body.response if kind=='reassessment' else 'documented'
        events.append(Event(id=f'SIM-{index+1}',kind=kind,occurred_at=at,available_at=at,value=value))
    now=START+timedelta(hours=body.elapsed_hours)
    case=Case(id='SIM',title='Управляемый учебный случай',age=59,ward='therapy',severity='nonsevere',events=events,review_times=[now])
    state=snapshot(case,now)
    checks=formal_checks(state)
    return {'snapshot':state,'formal_reference':checks.model_dump(),'temporal_facts':temporal_facts(state),
            'available_actions':[{'rule_id':c.rule_id,'action':allowed_action(c,state)} for c in checks.checks if allowed_action(c,state)],
            'assumptions':{'response':body.response,'origin':'Авторская ветка, выбранная до начала. Не рассчитана из препарата, дозы или вероятности исхода.',
                'scope':'Действия меняют события, начало отсчёта и проверку. Запись пересмотра сама по себе не меняет состояние пациента.',
                'clinical_validation':False},'api_jobs':0}
