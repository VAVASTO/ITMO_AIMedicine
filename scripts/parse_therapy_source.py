"""Download a pinned clinical source, extract page provenance and build local FTS.

Raw source text stays in data/private; only metadata and reviewed cards are public.
Install with pip install -e '.[research]'. No OCR: empty pages are reported explicitly.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--query', help='A literal word or phrase to search in the local PDF index')
    args = parser.parse_args()
    source = json.loads((ROOT/'research/therapy/documents.json').read_text())['primary'][0]
    path = ROOT/source['local_pdf']
    path.parent.mkdir(parents=True, exist_ok=True)
    if args.download and not path.exists():
        import httpx
        response = httpx.get(source['url'], timeout=60, follow_redirects=True)
        response.raise_for_status()
        if hashlib.sha256(response.content).hexdigest() != source['sha256']:
            raise SystemExit('Source version changed. Review the new document before updating the pinned hash.')
        path.write_bytes(response.content)
    if not path.exists():
        raise SystemExit('Source missing. Run with --download.')
    if hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
        raise SystemExit('Source checksum mismatch.')
    pages = [{'page':i+1,'text':p.extract_text() or ''} for i,p in enumerate(PdfReader(path).pages)]
    if len(pages) != source['pages']:
        raise SystemExit('Unexpected page count.')
    chunks = []
    for page in pages:
        # Chunks never cross a page; overlap preserves context at a boundary.
        text = page['text'].strip()
        for offset in range(0, len(text), 1500):
            chunk = text[offset:offset+1800]
            chunks.append({'id':f"CAP-2024-p{page['page']}-c{offset//1500+1}",
                           'page':page['page'],'offset':offset,'text':chunk,
                           'sha256':hashlib.sha256(chunk.encode()).hexdigest()})
    (path.parent/'cap-rro-2024-pages.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2))
    (path.parent/'cap-rro-2024-chunks.json').write_text(json.dumps(chunks,ensure_ascii=False,indent=2))
    with sqlite3.connect(path.parent/'clinical-index.db') as db:
        db.execute('DROP TABLE IF EXISTS chunks')
        db.execute('CREATE VIRTUAL TABLE chunks USING fts5(id UNINDEXED, page UNINDEXED, text, tokenize="unicode61")')
        db.executemany('INSERT INTO chunks VALUES (?,?,?)',[(c['id'],c['page'],c['text']) for c in chunks])
        db.commit()
        if args.query:
            query = '"'+args.query.replace('"','""')+'"'
            print(json.dumps([{'id':r[0],'page':r[1]} for r in db.execute(
                'SELECT id,page FROM chunks WHERE chunks MATCH ? ORDER BY bm25(chunks) LIMIT 5',(query,))],ensure_ascii=False))
    metadata = {'source_id':source['id'],'source_sha256':source['sha256'],'pages':len(pages),
        'chunks':len(chunks),'empty_pages':[p['page'] for p in pages if not p['text'].strip()],
        'parser':'pypdf 6.10.0','chunk_chars':1800,'stride_chars':1500,
        'visual_review_pages':[13,24,28,72,73],'visual_review_scope':'Проверены 4 используемых положения; страницы 72 и 73 визуально пустые. Весь PDF постранично не вычитан.',
        'retrieval':'SQLite FTS5 unicode61; keyword prototype, Russian stemming and OCR absent',
        'runtime_context':'4 manually reviewed paraphrase cards selected by exact rule ID; full-text search is a research tool'}
    (ROOT/'research/therapy/parsing-check.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(metadata,ensure_ascii=False))


if __name__ == '__main__': main()
