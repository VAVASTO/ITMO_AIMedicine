"""Export bounded precomputed views for a free static Space. No live model calls."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from itmo_aimedicine.config import ROOT
from itmo_aimedicine.expansion_api import catalog,all_cases,Evaluation,evaluate

ACTIONS=('treatment_review','history','allergy_review','renal_review')


def build():
    data={'catalog':catalog(),'views':{},'mode':'precomputed_static',
          'note':'Prepared results only. One extra record per view. No server, keys, model requests or arbitrary patient input.'}
    for case in all_cases():
        for index,time in enumerate(case.review_times):
            for assume in ([False,True] if case.provenance.get('type')=='synthea' else [False]):
                for action in ('none',*ACTIONS):
                    additions=[] if action=='none' else [dict(id='ui-1',kind=action,
                        code='medication_reconciliation' if action=='history' else '',
                        value='none_known' if action=='allergy_review' else 'documented',
                        occurred_at=time,available_at=time,details={})]
                    key=f'{case.id}|{index}|{int(assume)}|{action}'
                    data['views'][key]=evaluate(Evaluation(case_id=case.id,review_at=time,assume_therapy=assume,additions=additions))
    public=ROOT/'frontend/public';public.mkdir(exist_ok=True)
    source=public/'static-demo.json';source.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')))
    try:
        # Source mode is fixed at build time; this artifact has no API path fallback.
        import os
        env={**os.environ,'VITE_STATIC_DEMO':'1'}
        subprocess.run(['npm','run','build','--','--outDir','../.cache/static-demo-dist','--emptyOutDir'],cwd=ROOT/'frontend',env=env,check=True)
    finally:source.unlink(missing_ok=True)
    out=ROOT/'.cache/hf-static-demo'
    if out.exists():shutil.rmtree(out)
    out.mkdir(exist_ok=True,parents=True)
    shutil.copytree(ROOT/'.cache/static-demo-dist',out,dirs_exist_ok=True)
    index=(out/'index.html').read_text()
    for asset in (out/'assets').iterdir():
        index=index.replace('/assets/'+asset.name,'./'+asset.name)
        asset.rename(out/asset.name)
    (out/'assets').rmdir()
    (out/'index.html').write_text(index)
    (out/'README.md').write_text('''---
title: AIMedicine Therapy Demo
emoji: 🩺
colorFrom: blue
colorTo: gray
sdk: static
app_file: index.html
pinned: false
---

# AIMedicine: исследовательское демо

Пять направлений терапии. Все случаи синтетические. Показ заранее вычисленных
результатов; API-ключей и живых запросов нет. Клиническая проверка не проведена.
Создавать как Private Static Space. Платные ресурсы не нужны.
''')
    manifest={'type':'static','visibility_required':'private','server_required':False,'model_calls':0,
              'views':len(data['views']),'cases':len(data['catalog']['cases']),
              'limit':'One prepared additional record per snapshot; no arbitrary inputs or live inference.',
              'files':{str(p.relative_to(out)):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in out.rglob('*') if p.is_file()}}
    (ROOT/'research/therapy-expansion/static-package.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'views':manifest['views'],'files':len(manifest['files']),'bytes':sum(f['bytes'] for f in manifest['files'].values())}))


if __name__=='__main__':build()
