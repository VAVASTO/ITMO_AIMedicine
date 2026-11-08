"""Private local FTS index with document, PDF page and exact text offsets."""
import hashlib
import json
import sqlite3
from .config import ROOT
from .knowledge_search import terms
from .therapy_expansion import registry

INDEX=ROOT/'data/private/expansion-sources/search.db'


def build():
    rows=[];manifest=[]
    for source in registry()['sources']:
        if source['id']=='WORKFLOW':continue
        profile=source.get('text_prefix',source['profile'])
        path=ROOT/('data/private/sources/cap-rro-2024-pages.json' if profile=='CAP' else f'data/private/expansion-sources/{profile}.pages.json')
        pages=json.loads(path.read_text())
        for n,page in enumerate(pages,1):
            text=page['text'] if isinstance(page,dict) else page
            for offset in range(0,len(text),1000):
                chunk=text[offset:offset+1200]
                if chunk.strip():rows.append((source['id'],n,offset,chunk,hashlib.sha256(chunk.encode()).hexdigest()))
        manifest.append(dict(source_id=source['id'],pdf_pages=len(pages),text_pages=sum(bool((p['text'] if isinstance(p,dict) else p).strip()) for p in pages),pdf_sha256=source.get('sha256')))
    with sqlite3.connect(INDEX) as db:
        db.execute('DROP TABLE IF EXISTS passages')
        db.execute('CREATE VIRTUAL TABLE passages USING fts5(source UNINDEXED,page UNINDEXED,offset UNINDEXED,text,sha UNINDEXED,tokenize="unicode61")')
        db.executemany('INSERT INTO passages VALUES (?,?,?,?,?)',rows)
    result={'sources':manifest,'passages':len(rows),'chunk_chars':1200,'overlap_chars':200,'algorithm':'FTS5 prefix; document filter; one passage per page; not a clinical relevance model'}
    (ROOT/'research/therapy-expansion/parsing.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def search(query,source_id='all',limit=5):
    sources={s['id']:s for s in registry()['sources'] if s['id']!='WORKFLOW'}
    if source_id!='all' and source_id not in sources:raise ValueError('Unknown source')
    groups=terms(query)
    if not groups:return []
    if not INDEX.exists():raise FileNotFoundError(INDEX)
    match=' OR '.join('"'+t+'"*' for g in groups for t in g)
    with sqlite3.connect(f'file:{INDEX}?mode=ro',uri=True) as db:
        rows=db.execute('SELECT source,page,offset,text,sha FROM passages WHERE passages MATCH ? AND (?="all" OR source=?) ORDER BY bm25(passages) LIMIT 100',(match,source_id,source_id)).fetchall()
    output=[];seen=set()
    for sid,page,offset,text,sha in rows:
        if (sid,page) in seen:continue
        seen.add((sid,page))
        lowered=text.lower();first=min((lowered.find(t) for g in groups for t in g if t in lowered),default=0)
        start=max(0,first-60)
        output.append(dict(source_id=sid,page=int(page),offset=int(offset)+start,snippet=text[start:start+360],chunk_sha256=sha,url=sources[sid]['url']+f'#page={page}'))
        if len(output)>=limit:break
    return output
