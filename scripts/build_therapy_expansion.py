"""Build the versioned author benchmark; no model calls or clinical prevalence claims."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


PROFILES = {
    'CAP': dict(name='Внебольничная пневмония', scope='Нетяжёлая ВП у взрослых, терапевтический стационар',
                observations={'spo2':0}, labs={'cbc':0,'crp':0}, procedures={'chest_xray':0}, sources=['CAP2024']),
    'COPD': dict(name='ХОБЛ', scope='Госпитализация взрослого с обострением ХОБЛ',
                 observations={'spo2':0}, labs={'cbc':0,'crp':0}, procedures={'chest_xray':0,'ecg':0}, sources=['COPD2024']),
    'HTN': dict(name='Артериальная гипертензия', scope='Документированная АГ у взрослого, без гипертонического криза',
                observations={'blood_pressure':0,'heart_rate':0}, labs={'creatinine':365,'potassium':365,'glucose':365}, procedures={'ecg':365}, sources=['HTN2024']),
    'HF': dict(name='Хроническая сердечная недостаточность', scope='ХСН у взрослого, вне реанимации',
               observations={'blood_pressure':0,'heart_rate':0}, labs={'creatinine':0,'potassium':0,'sodium':0}, procedures={'ecg':0,'echo':365}, sources=['HF2024']),
    'DM2': dict(name='Сахарный диабет 2 типа', scope='СД2 у взрослого, без кетоацидоза и гиперосмолярного состояния',
                observations={'glucose':0}, labs={'hba1c':90,'egfr':365,'urine_acr':365}, procedures={'ecg':365,'foot_exam':365}, sources=['DM22022']),
}

CATEGORIES = [
    ('C01','Диагноз и анамнез'),('C02','Аллергоанамнез'),('C03','Наблюдения и жизненные показатели'),
    ('C04','Лабораторные исследования'),('C05','Инструментальные исследования и осмотры'),
    ('C06','Полнота и безопасность назначений'),('C07','Показания и начало лечения'),
    ('C08','Ответ на лечение и ухудшение'),('C09','План наблюдения'),('C10','Выписка и длительность лечения'),
]

# Contracts are supplied equally to both models. They are not expected answers.
RULES = [
 ('Q01','C01','Запись основного диагноза','workflow_hypothesis',['WORKFLOW'],'Current-admission diagnosis with code equal to primary: met, otherwise unknown.'),
 ('Q02','C01','Сверка постоянной терапии','workflow_hypothesis',['WORKFLOW'],'Current history event code medication_reconciliation: met, otherwise unknown.'),
 ('Q03','C02','Аллергоанамнез до назначения','workflow_hypothesis',['WORKFLOW'],'Known or none_known allergy_review must occur AND be available by first current order: met. If valid review exists only after first order: attention; no valid review: unknown. Without orders a valid current review is met.'),
 ('Q04','C03','Наличие выбранных наблюдений','clinical_projection',list(p['sources'][0] for p in PROFILES.values()),'Union profile observations. Every required code must have a nonempty value other than unknown/ordered within its lookback: met, otherwise unknown. Do not interpret numeric values.'),
 ('Q05','C04','Наличие выбранных анализов','clinical_projection',list(p['sources'][0] for p in PROFILES.values()),'Union profile labs. Every required code needs a completed result within its lookback: met, otherwise unknown. Orders alone do not count. This subset is not the complete clinical workup.'),
 ('Q06','C05','Наличие выбранных исследований','clinical_projection',list(p['sources'][0] for p in PROFILES.values()),'Union profile procedures. Every required code needs a documented result within lookback: met, otherwise unknown. Do not demand a repeat solely because a new admission occurred.'),
 ('Q07','C06','Заполненность назначения','workflow_hypothesis',['WORKFLOW'],'All current orders must have nonempty dose, route, frequency: met. Missing orders or any missing field: unknown. Do not assess dose correctness.'),
 ('Q08','C06','Совпадение с записанным аллергеном','workflow_hypothesis',['WORKFLOW'],'For each order use latest current allergy_review occurred AND available by order time. known requires comma-separated substances codes. Exact intersection with order code or class: attention. No valid prior review or empty known substances: unknown; otherwise met. No orders: not_applicable. No cross-reactivity inference.'),
 ('Q09','C06','Разбор терапии при почечном риске','workflow_hypothesis',['WORKFLOW'],'If renal_risk false or no current orders: not_applicable. Otherwise current renal_review: met, missing: unknown. No dose calculation or claim review preceded treatment.'),
 ('Q10','C07','Связь назначения с диагнозом','workflow_hypothesis',['WORKFLOW'],'Each current order indication_event_id must reference a current diagnosis available by order time: met, otherwise unknown. No orders: not_applicable. This only checks a link, not clinical appropriateness.'),
 ('Q11','C07','Срок назначения антибиотика при ВП','clinical_projection',['CAP2024'],'Primary CAP only, otherwise not_applicable. First antibiotic order on or after primary diagnosis: <=14400 seconds met, later attention. No order: pending if elapsed <=14400, unknown if later. No diagnosis: unknown. Use temporal_facts.'),
 ('Q12','C07','Назначение и фактическое введение','workflow_hypothesis',['WORKFLOW'],'Every current administration must reference order_id with same code, available by administration time: met, otherwise attention. No administrations: not_applicable.'),
 ('Q13','C08','Оценка ответа при ВП','clinical_projection',['CAP2024'],'Primary CAP only, otherwise not_applicable. A reassessment 172800..259200 seconds inclusive after first antibiotic administration: met. No start: unknown. Without timely reassessment: pending while elapsed <=259200; after deadline attention if a late assessment exists, otherwise unknown. Early assessment does not satisfy this window.'),
 ('Q14','C08','Разбор после ухудшения','workflow_hypothesis',['WORKFLOW'],'No current reassessment value worsening: not_applicable. A current treatment_review at or after latest worsening: met, otherwise attention. No causal claims.'),
 ('Q15','C09','Соблюдение записанного плана','workflow_hypothesis',['WORKFLOW'],'Latest current followup_plan with valid aware due_at. A reassessment referencing its plan_id, at/after plan and <=due: met. Otherwise pending if now<=due, unknown if overdue. No plan or invalid due: unknown. Do not invent interval.'),
 ('Q16','C10','Поля выписки','workflow_hypothesis',['WORKFLOW'],'No current discharge: not_applicable. Latest discharge requires nonempty details diagnosis, medication_plan, followup: met, otherwise unknown.'),
 ('Q17','C10','Длительность курса отдельно от госпитализации','workflow_hypothesis',['WORKFLOW'],'No medication_stop: not_applicable. Each stop must reference existing current administration start_id at/before stop: met, otherwise attention. Stay duration need not equal medication course. No clinical duration recommendation.'),
]


def build():
    sources = [
      dict(id='CAP2024',title='Внебольничная пневмония у взрослых',year=2024,profile='CAP',pdf_pages=[13,14,18,24,28],url='https://spulmo.ru/upload/KR-vnebolnichnaya-pnevmoniya-u-vzroslyh-2024.pdf',local='data/private/sources/cap-rro-2024.pdf',summary='В пилоте проверяю наличие SpO2, выбранных анализов и рентгенографии, срок назначения антибиотика и оценку ответа. Порог назначения 4 часа и окно оценки 48–72 часа перенесены в отдельные правила.'),
      dict(id='COPD2024',title='Хроническая обструктивная болезнь лёгких',year=2024,profile='COPD',pdf_pages=[23,50],url='https://spulmo.ru/upload/KR-HOBL.pdf',local='data/private/expansion-sources/COPD.pdf',summary='Для госпитализации с обострением выделил пульсоксиметрию, общий анализ крови, СРБ, рентгенографию и ЭКГ. Д-димер по показаниям не сделал безусловным требованием.'),
      dict(id='HTN2024',title='Артериальная гипертензия у взрослых',year=2024,profile='HTN',pdf_pages=[14,15,16],url='https://russjcardiol.elpub.ru/jour/article/download/6117/4464',local='data/private/expansion-sources/HTN.pdf',summary='Выделил записи АД и пульса, креатинина, калия, глюкозы и ЭКГ. Это часть обследования. Годовое окно давности в прототипе требует отдельного согласования.'),
      dict(id='HF2024',title='Хроническая сердечная недостаточность',year=2024,profile='HF',pdf_pages=[11,12,13],url='https://russjcardiol.elpub.ru/jour/article/download/6162/4522',local='data/private/expansion-sources/HF.pdf',summary='Выделил показатели наблюдения, креатинин, калий, натрий, ЭКГ и ЭхоКГ. Система ищет запись результата. Частоту повторных исследований и достаточность обследования оценивает врач.'),
      dict(id='DM22022',title='Сахарный диабет 2 типа у взрослых',year=2022,profile='DM2',pdf_pages=[151],url='https://rae-org.ru/system/files/documents/pdf/cr_dm_ii_ad_2022.pdf',local='data/private/expansion-sources/DM2.pdf',summary='Критерии включают HbA1c раз в три месяца, СКФ, альбуминурию, ЭКГ и осмотр стоп раз в год. В прототипе три месяца приближены 90 днями, год 365 днями. Это допущение для тестов.'),
      dict(id='DM2025',title='Алгоритмы специализированной медицинской помощи больным сахарным диабетом, 12-й выпуск',year=2025,profile='DM2',text_prefix='DM2025',pdf_pages=[14,46],url='https://www.dia-endojournals.ru/jour/article/download/13419/pdf_403',local='data/private/expansion-sources/DM2025.pdf',summary='Дополнительный документ 2025 года. Содержит обновлённые алгоритмы и данные регистра на 01.01.2025. Не подменяет статус клинической рекомендации в рубрикаторе; перенос лечебных алгоритмов в автоматические назначения не выполнен.'),
      dict(id='WORKFLOW',title='Исследовательский контракт полноты и последовательности записей v3',year=2026,profile=None,pdf_pages=[],url=None,summary='Авторские проверки связей и наличия записей. Не являются правовым заключением, перечнем штрафов или утверждёнными медицинскими критериями.'),
    ]
    for s in sources:
        if 'local' in s:
            path=ROOT/s.pop('local');s['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            s['current_revision_verified']=False
            s['revision_note']='Скачанная редакция проверена. Полнота поиска более новых редакций не подтверждена: рубрикатор не загрузил список.'
    registry={'version':'therapy-multi-v3','clinical_validation':False,'profiles':PROFILES,
              'categories':[dict(id=k,name=v) for k,v in CATEGORIES], 'sources':sources,
              'rules':[dict(id=i,category=c,title=t,basis=b,sources=s,contract=x) for i,c,t,b,s,x in RULES],
              'global_contract':'Adult therapy only; otherwise all not_applicable. Current means occurred_at >= admission_at. Only events occurred AND available by review are visible. A current exception whose code is a rule ID overrides that rule to unknown. Profile lookback=0 means since admission; positive days means review_at minus days. Shared codes use the shortest lookback. These are research windows, not automatic orders for repeat tests. Source documents and workflow checks are not a clinical gold standard.'}
    write(ROOT/'research/therapy-expansion/catalog.json',registry)
    generated=[]; labels=[]
    start=datetime(2026,11,1,8,tzinfo=timezone(timedelta(hours=3)))
    for i,(profile,p) in enumerate(PROFILES.items(),1):
        for variant in ('complete','gap','delayed'):
            cid=f'M{i:02d}-{variant}';events=[];sequence=[0]
            def add(kind,code='',value='documented',hour=0,details=None,available=None):
                sequence[0]+=1
                eid=f'e{sequence[0]:02d}'
                events.append(dict(id=eid,kind=kind,code=code,value=value,occurred_at=(start+timedelta(hours=hour)).isoformat(),available_at=(start+timedelta(hours=available if available is not None else hour)).isoformat(),details=details or {}))
                return eid
            diagnosis=add('diagnosis',profile)
            add('history','medication_reconciliation',hour=.1)
            allergy=add('allergy_review',value='none_known',hour=.2)
            for field,kind in [('observations','observation'),('labs','lab'),('procedures','procedure')]:
                for code in p[field]:add(kind,code,hour=1)
            drug='synthetic-antibiotic' if profile=='CAP' else 'synthetic-medication'
            order=add('order',drug,hour=2,details={'class':'antibiotic' if profile=='CAP' else 'other','dose':'recorded_by_clinician','route':'recorded_by_clinician','frequency':'recorded_by_clinician','indication_event_id':diagnosis})
            admin=add('administration',drug,hour=3,details={'class':'antibiotic' if profile=='CAP' else 'other','order_id':order})
            plan=add('followup_plan',hour=4,details={'due_at':(start+timedelta(hours=63)).isoformat()})
            add('reassessment',value='improving',hour=51,details={'plan_id':plan})
            add('renal_review',hour=4)
            add('medication_stop',drug,hour=96,details={'start_id':admin})
            add('discharge',hour=120,details={'diagnosis':profile,'medication_plan':'Записан врачом','followup':'Записан врачом'})
            if variant=='gap':
                events=[e for e in events if not (e['kind'] in ('allergy_review','lab','renal_review') or e['kind']=='reassessment')]
                add('reassessment',value='worsening',hour=55)
            if variant=='delayed':
                for e in events:
                    if e['kind'] in ('lab','reassessment'):e['available_at']=(start+timedelta(hours=130)).isoformat()
            case=dict(id=cid,patient_id=f'author-{i:02d}-{variant}',title=p['name']+': '+{'complete':'полная запись','gap':'пробелы и ухудшение','delayed':'запоздалые записи'}[variant],age=50+i*4,primary=profile,comorbidities=[],renal_risk=profile=='DM2',ward='therapy',admission_at=start.isoformat(),review_times=[(start+timedelta(hours=x)).isoformat() for x in (2,60,121,131)],events=events,provenance={'type':'authored_benchmark','sampling':'equal profiles; not a prevalence estimate','clinical_validation':'false'})
            generated.append(case)
            # Independent, hand-specified 121-hour expectations, not calculated from check().
            expected={f'Q{n:02d}':'met' for n in range(1,18)}
            if profile!='CAP':expected.update(Q11='not_applicable',Q13='not_applicable')
            expected['Q09']='met' if profile=='DM2' else 'not_applicable'
            expected['Q14']='not_applicable'
            if variant=='gap':
                expected.update(Q03='unknown',Q05='unknown',Q08='unknown',Q14='attention',Q15='unknown')
                if profile=='CAP':expected['Q13']='met'
                if profile=='DM2':expected['Q09']='unknown'
            if variant=='delayed':
                expected.update(Q05='unknown',Q15='unknown')
                if profile=='CAP':expected['Q13']='unknown'
            labels.append(dict(case_id=cid,review_at=case['review_times'][2],statuses=expected))
    write(ROOT/'data/therapy-expansion/cases.json',generated)
    write(ROOT/'data/therapy-expansion/expectations.json',{'author_labels':True,'clinical_validation':False,'snapshots':labels})
    print('Built 5 profiles, 10 categories, 17 rules, 15 cases; no API calls.')


if __name__=='__main__':build()
