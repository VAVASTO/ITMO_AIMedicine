import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from itmo_aimedicine.config import ROOT
from itmo_aimedicine.knowledge_search import build_index, search, literal_search

metadata=build_index()
queries=json.loads((ROOT/'research/therapy/search-queries.json').read_text())
results=[]
for item in queries['queries']:
    old=literal_search(item['query'])
    new=[r['page'] for r in search(item['query'])]
    row={**item,'literal_pages':old,'revised_pages':new}
    for name,pages in [('literal',old),('revised',new)]:
        row[name+'_hit1']=bool(set(pages[:1])&set(item['pages'])) if item['pages'] else None
        row[name+'_hit3']=bool(set(pages[:3])&set(item['pages'])) if item['pages'] else None
        row[name+'_abstained']=not pages
    results.append(row)
output={'metadata':metadata,'scope':'inpatient','label_origin':queries['label_origin'],'results':results,
        'limits':'Queries were frozen before the initial evaluation. Numeric/abbreviation matching and inpatient filtering were then refined; all queries now form a regression set, not an untouched holdout. Four intents, no general clinical retrieval claim.'}
(ROOT/'research/therapy/search-check.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(output,ensure_ascii=False))
