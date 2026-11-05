"""Computed temporal facts and independent model roles; no expected labels in prompts."""
from datetime import datetime

from .longitudinal import (Audit, Plan, Event, cards, snapshot, formal_checks,
                           consistency, prompts as v1_prompts, validate_links)

VERSION = 'therapy-cap-v2'


def temporal_facts(state):
    """Derive durations from visible events only, in seconds to preserve boundaries."""
    now = datetime.fromisoformat(state['review_at'])
    events = sorted((Event.model_validate(e) for e in state['events']),
                    key=lambda e: (e.occurred_at, e.id))
    if any(e.occurred_at > now or e.available_at > now for e in events):
        raise ValueError('Future or unavailable event in snapshot')
    diagnoses = [e for e in events if e.kind == 'diagnosis' and e.value == 'confirmed_cap']
    diagnosis = diagnoses[0] if diagnoses else None
    relevant = [e for e in events if diagnosis and e.occurred_at >= diagnosis.occurred_at]
    first = lambda kind: next((e for e in relevant if e.kind == kind), None)
    order, start = first('antibiotic_order'), first('antibiotic_start')
    seconds = lambda end, begin: (end - begin).total_seconds() if begin else None
    assessments = [e for e in relevant if e.kind == 'reassessment' and start and e.occurred_at >= start.occurred_at]
    worsening = [e for e in assessments if e.value == 'worsening']
    last = worsening[-1] if worsening else None
    return {
        'units': 'seconds; 4h=14400, 48h=172800, 72h=259200; boundaries inclusive',
        'diagnosis_id': diagnosis.id if diagnosis else None,
        'first_order_id': order.id if order else None,
        'first_start_id': start.id if start else None,
        'review_since_diagnosis_seconds': seconds(now, diagnosis.occurred_at) if diagnosis else None,
        'order_since_diagnosis_seconds': seconds(order.occurred_at, diagnosis.occurred_at) if order else None,
        'review_since_start_seconds': seconds(now, start.occurred_at) if start else None,
        'assessment_intervals': [{'event_id': e.id, 'since_start_seconds': seconds(e.occurred_at, start.occurred_at)} for e in assessments],
        'latest_worsening_id': last.id if last else None,
        'reviews_after_latest_worsening': [e.id for e in relevant if last and e.kind == 'treatment_review' and e.occurred_at >= last.occurred_at],
        'exceptions_by_rule': {r: [e.id for e in events if e.kind == 'exception' and e.rule_id == r]
                               for r in ('CAP01', 'CAP02', 'CAP03', 'CAP04')},
    }


def prompts(role):
    # Keep v1 source contracts intact so the comparison changes only this bundle.
    return v1_prompts(role) + '''
V2: temporal_facts are computed by code from this snapshot, not labels or model judgments.
Use these exact durations instead of subtracting dates yourself. Compare seconds to the stated
inclusive thresholds: exactly 259200 seconds is still within 72h. Missing timestamps stay null.
Exceptions affect ONLY their own rule; do not transfer an exception to any other rule.
The audit receives no draft plan. Assess recorded events independently of the recommendation role.
In explanations cite event IDs and the computed interval when useful; do not invent elapsed times.
'''


def payload(state):
    return {'state': state, 'source_cards': cards(), 'temporal_facts': temporal_facts(state)}


def run_pipeline(case, review_at, provider):
    state = snapshot(case, review_at)
    data = payload(state)
    plan = provider.complete(prompts('recommend'), data, Plan)
    validate_links(plan.result, state, data['source_cards'])
    audit = provider.complete(prompts('audit'), data, Audit)
    validate_links(audit.result, state, data['source_cards'])
    checks = consistency(plan.result, audit.result, state)
    return {'version': VERSION, 'snapshot': state, 'temporal_facts': data['temporal_facts'],
            'plan': plan.as_dict(), 'audit': audit.as_dict(),
            'formal_reference': formal_checks(state).model_dump(), 'clinical_validation': False,
            'consistency': checks,
            'review_required': bool(checks['audit_disagreements'] or checks['plan_disagreements'])}
