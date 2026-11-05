"""Local page-grounded retrieval; source text is never sent to a model automatically."""
import hashlib
import json
import re
import sqlite3

from .config import ROOT

FOLDER = ROOT/'data/private/sources'
INDEX = FOLDER/'clinical-search-v2.db'
STOP = set('и в во на с со при по для как когда через сколько какой какие что это ли или к от до после у не из лечение лечения пациентов пациенту'.split())
SYNONYMS = {'стационар':['стационар','госпитализ'], 'spo2':['пульсоксиметр','сатурац','spo2'], 'сатурац':['пульсоксиметр','сатурац'],
            'антибиотик':['антибиот','аб','антибактериальн'], 'антибактериальн':['антибиот','аб','антибактериальн']}


def terms(query):
    output=[]
    for token in re.findall(r'[a-zа-яё0-9]+',query.lower().replace('ё','е')):
        if token in STOP or (len(token)<2 and not token.isdigit()): continue
        expansion=next((values for root,values in SYNONYMS.items() if token.startswith(root)),None)
        output.append(expansion or [token[:6] if len(token)>6 else token])
    return output[:16]


def section(page):
    # Page ranges describe document structure, not query relevance. Mixed pages
    # retain a broad section label; this is not paragraph-level clinical metadata.
    if page<5: return 'frontmatter'
    if page<12: return 'background'
    if page<21: return 'diagnostics'
    if page<24: return 'outpatient'
    if page<36: return 'inpatient'
    if page<38: return 'prevention'
    if page<43: return 'organization'
    if page<58: return 'references'
    return 'appendix'


def build_index():
    metadata=json.loads((ROOT/'research/therapy/documents.json').read_text())['primary'][0]
    pdf=ROOT/metadata['local_pdf']
    if hashlib.sha256(pdf.read_bytes()).hexdigest()!=metadata['sha256']:
        raise ValueError('Source checksum mismatch')
    pages=json.loads((FOLDER/'cap-rro-2024-pages.json').read_text())
    chunks=[]
    for page in pages:
        text=page['text']
        # End at a line boundary where possible; preserve exact character offsets.
        offset=0
        while offset<len(text):
            end=min(offset+1200,len(text))
            if end<len(text):
                boundary=text.rfind('\n',offset+600,end)
                if boundary!=-1: end=boundary+1
            raw=text[offset:end]
            if raw.strip():
                chunks.append((f"CAP-2024-p{page['page']}-o{offset}",page['page'],section(page['page']),offset,raw,
                               hashlib.sha256(raw.encode()).hexdigest()))
            if end==len(text): break
            offset=max(offset+1,end-200)
    with sqlite3.connect(INDEX) as db:
        db.execute('DROP TABLE IF EXISTS passages')
        db.execute('CREATE VIRTUAL TABLE passages USING fts5(id UNINDEXED,page UNINDEXED,section UNINDEXED,offset UNINDEXED,text,sha UNINDEXED,tokenize="unicode61")')
        db.executemany('INSERT INTO passages VALUES (?,?,?,?,?,?)',chunks)
    return {'source_sha256':metadata['sha256'],'passages':len(chunks),'max_chars':1200,'overlap_chars':200,
            'algorithm':'FTS5 prefix + short synonym list, term coverage, recommendation marker, section filter; no embeddings',
            'section_metadata':'Page ranges, mixed pages may contain adjacent sections',
            'current_version_verified':metadata['current_version_verified'],'clinical_approval':False}


def search(query, scope='inpatient', limit=5):
    if scope not in {'clinical','inpatient','all'}: raise ValueError('Unknown search scope')
    groups=terms(query)
    if not groups: return []
    if not INDEX.exists(): raise FileNotFoundError('Build the local search index first')
    match=' OR '.join('"'+term+'"*' for group in groups for term in group)
    where={'clinical':"AND section NOT IN ('frontmatter','references','appendix')",
           'inpatient':"AND section IN ('diagnostics','inpatient','organization')",'all':''}[scope]
    with sqlite3.connect(f'file:{INDEX}?mode=ro',uri=True) as db:
        rows=db.execute(f'SELECT id,page,section,offset,text,sha,bm25(passages) FROM passages WHERE passages MATCH ? {where} ORDER BY bm25(passages) LIMIT 1000',(match,)).fetchall()
    candidates=[]
    for id,page,part,offset,text,sha,rank in rows:
        normalized=text.lower().replace('ё','е')
        tokens=re.findall(r'[a-zа-я0-9]+',normalized)
        coverage=sum(any(any(word==term if term.isdigit() else word.startswith(term) for word in tokens) for term in group) for group in groups)/len(groups)
        if coverage<.5: continue
        first=min((normalized.find(term) for group in groups for term in group if term in normalized),default=0)
        start=max(0,first-70)
        candidates.append({'id':id,'page':int(page),'section':part,'offset':int(offset),'sha256':sha,
            'snippet':' '.join(text[start:start+360].split()),'coverage':round(coverage,3),'rank':rank,'recommendation':bool(re.search(r'рекомендуется|необходимо',normalized)),
            'url':f'https://spulmo.ru/upload/KR-vnebolnichnaya-pnevmoniya-u-vzroslyh-2024.pdf#page={page}',
            'source_id':'CAP-2024','clinical_approval':False})
    candidates.sort(key=lambda row:(-row['coverage'],-int(row['recommendation']),row['rank'],row['page']))
    # One result per page makes a short list useful; retain the best chunk's provenance.
    output=[];seen=set()
    for row in candidates:
        if row['page'] in seen: continue
        seen.add(row['page']); row.pop('rank'); row.pop('recommendation'); output.append(row)
        if len(output)==limit: break
    return output


def literal_search(query,limit=5):
    with sqlite3.connect(f'file:{FOLDER/"clinical-index.db"}?mode=ro',uri=True) as db:
        return [int(r[0]) for r in db.execute('SELECT page FROM chunks WHERE chunks MATCH ? ORDER BY bm25(chunks) LIMIT ?',
            ('"'+query.replace('"','""')+'"',limit))]
