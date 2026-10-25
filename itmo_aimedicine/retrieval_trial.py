"""Lexical ranking versus exact extraction when the routing keys are known."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

from .config import ROOT


def tokens(text):
    return re.findall(r'[\w]+',text.casefold())


def searchable(item):
    return ' '.join([item.get('query',item.get('text','')),item['topic'],item['scope'],item['revision']])


def rank_bm25(query, corpus):
    docs=[tokens(searchable(d)) for d in corpus]
    terms=tokens(searchable(query));n=len(docs)
    mean=sum(map(len,docs))/n
    results=[]
    for item,doc in zip(corpus,docs):
        counts=Counter(doc);score=0.0
        for term in set(terms):
            df=sum(term in d for d in docs);tf=counts[term]
            idf=math.log(1+(n-df+0.5)/(df+0.5))
            if tf:score+=idf*tf*2.5/(tf+1.5*(0.25+0.75*len(doc)/mean))
        results.append((score,item['id']))
    return [ident for score,ident in sorted(results,key=lambda x:(-x[0],x[1])) if score>0]


def exact_lookup(query,corpus):
    return [d['id'] for d in corpus if all(d[k]==query[k] for k in ('topic','scope','revision'))]


def run():
    folder=ROOT/'data/research/comparison-v1'
    packet=json.loads((folder/'retrieval.json').read_text())
    labels={r['query_id']:set(r['relevant_ids']) for r in json.loads((folder/'retrieval-expectations.json').read_text())}
    corpus=packet['corpus'];by_id={d['id']:d for d in corpus};records=[]
    for query in packet['queries']:
        for method in ('bm25_all','bm25_scope_version_filter','exact_known_keys'):
            subset=[d for d in corpus if d['scope']==query['scope'] and d['revision']==query['revision']] if method=='bm25_scope_version_filter' else corpus
            ranked=exact_lookup(query,subset) if method=='exact_known_keys' else rank_bm25(query,subset)
            relevant=labels[query['id']]
            records.append({'query_id':query['id'],'method':method,'ranked_ids':ranked,
                'recall_at_1':len(set(ranked[:1])&relevant)/len(relevant),
                'recall_at_3':len(set(ranked[:3])&relevant)/len(relevant),
                'inapplicable_in_top3':sum(by_id[x]['scope']!=query['scope'] or by_id[x]['revision']!=query['revision'] for x in ranked[:3])})
    summary={}
    for method in ('bm25_all','bm25_scope_version_filter','exact_known_keys'):
        rows=[r for r in records if r['method']==method]
        summary[method]={'queries':len(rows),'top1_hits':sum(r['recall_at_1']==1 for r in rows),'top3_hits':sum(r['recall_at_3']==1 for r in rows),'inapplicable_top3_total':sum(r['inapplicable_in_top3'] for r in rows)}
    result={'purpose':packet['purpose'],'api_calls':0,'bm25':{'k1':1.5,'b':0.75,'tokenization':'lowercase Unicode word tokens; no stemming'},
            'input_sha256':hashlib.sha256((folder/'retrieval.json').read_bytes()).hexdigest(),
            'expectations_sha256':hashlib.sha256((folder/'retrieval-expectations.json').read_bytes()).hexdigest(),
            'summary':summary,'records':records,
            'limitations':['All methods receive the same query plus manually supplied topic, scope and revision.',
                          'Exact extraction assumes a correct upstream router; that router is not tested.',
                          'Nine authored cards and twelve authored queries; not clinical documents or an independent retrieval benchmark.',
                          'No embeddings, hybrid search or reranker comparison; no latency claim.']}
    (ROOT/'reports/checks/retrieval-comparison-2026-10-25.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':run()
