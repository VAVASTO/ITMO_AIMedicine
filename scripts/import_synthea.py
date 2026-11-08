"""Import official Synthea CSV without inventing a Russian ward or missing care."""
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
import csv
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from itmo_aimedicine.config import ROOT
from itmo_aimedicine.therapy_expansion import Encounter

PROFILES={'233604007':'CAP','87433001':'COPD','185086009':'COPD',
          '59621000':'HTN','88805009':'HF','84114007':'HF','44054006':'DM2'}
OBS={'59408-5':('observation','spo2'),'2708-6':('observation','spo2'),
     '8480-6':('observation','systolic_bp'),'8462-4':('observation','diastolic_bp'),
     '8867-4':('observation','heart_rate'),'2339-0':('lab','glucose'),
     '2345-7':('lab','glucose'),'4548-4':('lab','hba1c'),
     '2160-0':('lab','creatinine'),'33914-3':('lab','egfr'),
     '2823-3':('lab','potassium'),'2951-2':('lab','sodium'),
     '14959-1':('lab','urine_acr')}


def dt(value):
    t=datetime.fromisoformat(value.replace('Z','+00:00'))
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    folder=ROOT/'data/private/synthea-run/csv'
    tables={p.stem:list(csv.DictReader(p.open())) for p in folder.glob('*.csv')}
    patients={r['Id']:r for r in tables['patients']}
    by_patient=defaultdict(list)
    for r in tables['conditions']:by_patient[r['PATIENT']].append(r)
    encounter_rows=defaultdict(lambda:defaultdict(list))
    for name in ('conditions','observations','medications','procedures','allergies'):
        for r in tables[name]:encounter_rows[r['ENCOUNTER']][name].append(r)
    ever={p:set() for p in ('CAP','COPD','HTN','HF','DM2')}
    for r in tables['conditions']:
        if r['CODE'] in PROFILES:ever[PROFILES[r['CODE']]].add(r['PATIENT'])
    selected=defaultdict(list);eligible=Counter();raw=[]
    for e in sorted(tables['encounters'],key=lambda x:x['START'],reverse=True):
        p=patients[e['PATIENT']];start=dt(e['START']);birth=dt(p['BIRTHDATE'])
        age=start.year-birth.year-((start.month,start.day)<(birth.month,birth.day))
        if age<18:continue
        rows=encounter_rows[e['Id']]
        profile=PROFILES.get(e['REASONCODE'])
        selection='encounter_reason'
        if profile is None:
            profile=next((PROFILES[r['CODE']] for r in rows['conditions'] if r['CODE'] in PROFILES),None)
            selection='first_mapped_condition_at_encounter_not_confirmed_primary'
        if not profile:continue
        eligible[(profile,e['ENCOUNTERCLASS'])]+=1
        raw.append((e,p,age,profile,selection))
    # Prefer inpatient examples without hiding missing profile coverage.
    raw.sort(key=lambda x:(x[0]['ENCOUNTERCLASS']!='inpatient',-dt(x[0]['START']).timestamp()))
    imported=[]
    for e,p,age,profile,selection in raw:
        if len(selected[profile])>=2 or e['PATIENT'] in selected[profile]:continue
        selected[profile].append(e['PATIENT']);rows=encounter_rows[e['Id']]
        start=dt(e['START']);end=dt(e['STOP']);events=[]
        def add(kind,code,value,at,details=None):
            # CSV has no separate recording timestamp; availability=event is an explicit assumption.
            events.append(dict(id=f's{len(events)+1:04d}',kind=kind,code=code,value=value,
                occurred_at=at.isoformat(),available_at=at.isoformat(),details=details or {}))
        for r in rows['conditions']:
            if r['CODE'] in PROFILES:
                add('diagnosis',PROFILES[r['CODE']],r['DESCRIPTION'],dt(r['START']),{'source_code':r['CODE'],'precision':'day'})
        if e['REASONCODE'] in PROFILES and not any(x['code']==profile for x in events):
            add('diagnosis',profile,e['REASONDESCRIPTION'],start,{'source_code':e['REASONCODE'],'origin':'encounter_reason'})
        for r in rows['observations']:
            if r['CODE'] in OBS:
                kind,code=OBS[r['CODE']];add(kind,code,r['VALUE'],dt(r['DATE']),{'unit':r['UNITS'],'source_code':r['CODE']})
        for r in rows['medications']:
            # Medication CSV denotes a prescription. It does not prove administration.
            add('order','rxnorm:'+r['CODE'],r['DESCRIPTION'],dt(r['START']),{'origin':'medications.csv','class':'unmapped'})
        # Never turn absence of allergy rows into a negative allergy history.
        for r in rows['allergies']:
            add('history','coded_allergy',r['DESCRIPTION'],dt(r['START']),{'source_code':r['CODE'],'system':r['SYSTEM']})
        if end>=start:add('discharge',value='Encounter ended; discharge document not exported',code='',at=end)
        comorbid=sorted({PROFILES[r['CODE']] for r in by_patient[e['PATIENT']] if r['CODE'] in PROFILES and
                        dt(r['START'])<=start and (not r['STOP'] or dt(r['STOP'])>start)}-{profile})
        case=Encounter.model_validate(dict(id=f'SYN-{profile}-{len(selected[profile])}',patient_id='syn-'+hashlib.sha256(e['PATIENT'].encode()).hexdigest()[:12],
          title=f'Synthea · {profile} · {e["ENCOUNTERCLASS"]}',age=age,primary=profile,comorbidities=comorbid,
          renal_risk=any('kidney' in r['DESCRIPTION'].lower() and dt(r['START'])<=start and (not r['STOP'] or dt(r['STOP'])>start) for r in by_patient[e['PATIENT']]),
          ward='other',admission_at=start,review_times=[start,max(end,start)+timedelta(seconds=1)],events=events,
          provenance={'type':'synthea','country':'US','encounter_class':e['ENCOUNTERCLASS'],'primary_selection':selection,
                      'ward_mapping':'unknown; therapy requires explicit educational assumption',
                      'availability':'equal to event time; CSV lacks recording timestamp',
                      'no_imputed_data':'No doses, administrations, negative allergies or Russian documentation invented'}))
        imported.append(case.model_dump(mode='json'))
    out=ROOT/'data/therapy-expansion/synthea-cases.json';out.write_text(json.dumps(imported,ensure_ascii=False,indent=2)+'\n')
    manifest={'generator':'Synthea','repository':'https://github.com/synthetichealth/synthea',
       'release':'master-branch-latest',
       'release_published_at':'2026-10-21T23:19:27Z','asset_id':664072215,
       'asset_url':'https://github.com/synthetichealth/synthea/releases/download/master-branch-latest/synthea-with-dependencies.jar',
       'jar_sha256':sha(ROOT/'.cache/tools/synthea-with-dependencies.jar'),
       'seed':20261108,'clinician_seed':20261108,'reference_date':'2026-11-08','requested_alive_population':100,'requested_age_range':[35,85],
       'java':'Temurin 17.0.21+9','thread_pool_size':1,'region':'Massachusetts (default)',
       'patients_exported':len(patients),'alive_exported':sum(not r['DEATHDATE'] for r in patients.values()),
       'deceased_exported':sum(bool(r['DEATHDATE']) for r in patients.values()),
       'encounter_classes':dict(Counter(r['ENCOUNTERCLASS'] for r in tables['encounters'])),
       'patients_ever_with_profile':{k:len(v) for k,v in ever.items()},
       'mapped_adult_encounters':[{'profile':k[0],'encounter_class':k[1],'count':v} for k,v in sorted(eligible.items())],
       'imported_cases':len(imported),'imported_profiles':dict(Counter(c['primary'] for c in imported)),
       'rows':{k:len(v) for k,v in tables.items()},'csv_sha256':{p.name:sha(p) for p in folder.glob('*.csv')},
       'public_cases_sha256':sha(out),'clinical_validation':False,
       'limitations':['US synthetic population; not Russian prevalence or clinical validation.',
         'Historical ever-diagnosed counts are not current prevalence or admission proportions.',
         'CSV export has day-precision conditions and no availability timestamps.',
         'Russian therapy ward and clinical severity are unknown; imported records remain outside scope by default.',
         'No Russian diagnosis prevalence calibration performed. Profiles overlap.'],
       'split':'Author benchmark and Synthea import kept separate; no patient shared with authored model comparison.'}
    (ROOT/'research/therapy-expansion/synthea-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:manifest[k] for k in ('patients_exported','alive_exported','deceased_exported','patients_ever_with_profile','imported_cases','imported_profiles')}))


if __name__=='__main__':main()
