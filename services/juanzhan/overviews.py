"""Shared, bounded source-only overview. No model, writes, or inferred business fields."""
import json
import re
from fastapi import HTTPException
from .auth import fail
from .content import read_rows, selected
from .document_api import project
from .source_paths import SourceMounts
from .storage import ManagedStore

VERSION='extractive-v2'

def shorten(text,limit=140):
    return text[:limit].rstrip()+'…' if len(text)>limit else text

def text_of(block):
    table=block.get('structure',{}).get('table')
    if block['type']=='table' and table:
        headers=table.get('headers') or []
        return '；'.join('；'.join((str(headers[i])+'：' if i<len(headers) else '')+str(cell) for i,cell in enumerate(row)) for row in table.get('rows',[])[:2])
    return block.get('text','')

def compact(blocks):
    return {**blocks[0],'text':'；'.join(block['text'] for block in blocks),'source_blocks':blocks}

def excerpt(text):
    match=re.match(r'^.*?[。！？!?]',text)
    return shorten((match[0] if match else text).strip())

def summarize(data,title='文档'):
    source=data['body'][:100]
    blocks=[{**block,'text':re.sub(r'[ \t]+',' ',text_of(block)[:4000]).strip()} for block in source]
    blocks=[block for block in blocks if block['text']]
    points=[];seen=set();omitted=any(len(block.get('structure',{}).get('table',{}).get('rows',[]))>2 for block in source)
    def add(label,candidates,anchor):
        nonlocal omitted
        unique=[block for block in candidates if block['text']!=label and block['text'] not in seen]
        chosen=unique[:2]
        if not label and not chosen:return
        if len(points)>=8:omitted=True;return
        seen.update(block['text'] for block in chosen)
        evidence=[anchor]
        for block in chosen:evidence.extend(block.get('source_blocks',[block]))
        sources=[];indices=set()
        for block in evidence:
            if block['index'] in indices:continue
            indices.add(block['index'])
            sources.append({'index':block['index'],'block_id':block.get('id'),'text':shorten(block['text'],400),
                            'locator':block.get('locator',{'kind':'unknown'})})
        points.append({'label':shorten(label,100),'details':[excerpt(block['text']) for block in chosen],
                       'index':anchor['index'],'sources':sources})
        if len(unique)>len(chosen) or any(excerpt(block['text'])!=block['text'] for block in chosen):omitted=True
    first=next((i for i,block in enumerate(blocks) if block['type']=='heading'),-1)
    if first<0:
        for block in blocks:
            for text in filter(None,re.split(r'(?<=[。！？!?])\s*|\n+',block['text'])):
                add('',[{**block,'text':text}],block)
    else:
        lead=blocks[:first]
        if lead:add('',[compact(lead[:4])],lead[0])
        headings=[block for block in blocks if block['type']=='heading']
        def level(block):return block.get('structure',{}).get('level') or 1
        minimum=min(map(level,headings));roots=[block for block in headings if level(block)==minimum]
        if len(roots)==1 and blocks[0] is roots[0] and len(headings)>1:
            following=[block for block in headings if block is not roots[0]]
            minimum=min(map(level,following))
            intro=blocks[1:next(i for i,block in enumerate(blocks) if block is following[0])]
            add(roots[0]['text'],[compact(intro[:4])] if intro else [],roots[0])
        sections=[(i,block) for i,block in enumerate(blocks) if block['type']=='heading' and level(block)==minimum]
        for position,(index,block) in enumerate(sections):
            children=blocks[index+1:sections[position+1][0] if position+1<len(sections) else len(blocks)]
            topics=[child for child in children if child['type']=='heading']
            prose=[child for child in children if child['type']!='heading']
            add(block['text'],([compact(topics[:4])] if topics else [])+prose,block)
    return {'title':re.sub(r'\.[A-Za-z0-9]{1,8}$','',title),'method':VERSION,'points':points,'omitted':omitted,
            'partial':data['total']>len(source) or any(len(text_of(block))>4000 for block in source),
            'covered':len(source),'total':data['total']}

def view(db,settings,id,run_id=None):
    doc=project(db,id,ManagedStore(settings.data_dir/'managed'),SourceMounts(settings.source_mounts))
    base={'document_id':id,'document_version':doc['document_version'],'current_revision_id':doc['current_revision_id'],
          'content_revision_id':None,'parse_run_id':None,'processing_status':doc['processing_status'],
          'availability_status':doc['availability_status'],'warnings':[],'text_available':False,'ocr_used':False,
          'stale_for_current_revision':False}
    if not doc['current_parse_run_id'] and not run_id:
        return {**base,**summarize({'body':[],'total':0},doc['title'])}
    run=selected(db,doc,run_id)
    if run['status']!='completed':fail(409,'CONTENT_NOT_COMPLETED','This run has no successful content')
    total=db.execute('SELECT count(*) FROM content_blocks WHERE parse_run_id=?',(run['id'],)).fetchone()[0]
    sql='SELECT block_id,block_index,block_type,substr(text_content,1,4001) AS text_content,structural_json,locator_json FROM content_blocks WHERE parse_run_id=? ORDER BY block_index LIMIT ?'
    try:rows=read_rows(db,sql,(run['id'],100),('text_content','structural_json','locator_json'))
    except HTTPException as exc:
        if exc.status_code!=413:raise
        rows=read_rows(db,sql,(run['id'],20),('text_content','structural_json','locator_json'))
    blocks=[{'id':row['block_id'],'index':row['block_index'],'type':row['block_type'],'text':row['text_content'],
             'structure':json.loads(row['structural_json']),'locator':json.loads(row['locator_json'])} for row in rows]
    return {**base,**summarize({'body':blocks,'total':total},doc['title']),
            'content_revision_id':run['revision_id'],'parse_run_id':run['id'],'warnings':json.loads(run['warnings_json']),
            'ocr_used':bool(run['ocr_used']),'text_available':bool(run['text_available']),
            'stale_for_current_revision':bool(doc['content_stale'] or run['id']!=doc['current_parse_run_id'] or run['revision_id']!=doc['current_revision_id'] or doc['availability_status'] in ('source_offline','missing','suspected_missing','needs_match'))}
