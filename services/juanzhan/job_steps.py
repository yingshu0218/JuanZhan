"""Small ordered progress records, updated under the owning job lease."""
import json

PARSE_STEPS = ('validate', 'submit', 'extract', 'assets', 'publish')


def initial(job):
    if job['target_type']=='document_snapshot':codes=('validate','copy','publish')
    elif job['target_type']=='document_reading_preview':codes=('validate','render','publish')
    else:codes = PARSE_STEPS if job['kind'] in ('parse', 'ocr') and job['target_type']=='document' else ('process',)
    return [{'code':code,'status':'pending','done':0,'total':None} for code in codes]


def finish(db, job, status):
    steps = json.loads(job['steps_json'])
    for step in steps:
        if step['status']=='running':
            step['status']=status
            if status=='completed':
                step['done']=step['total'] if step['total'] is not None else 1
                step['total']=step['total'] if step['total'] is not None else 1
    db.execute('UPDATE jobs SET steps_json=? WHERE id=?',(json.dumps(steps),job['id']))


def enrich(db, job, result):
    """Use the captured revision name, never an external source's absolute path."""
    result['document_name']=None
    if job['target_type'] in ('document','document_search','document_snapshot','document_reading_preview','document_revision_cleanup') and job['target_id']:
        revision=json.loads(job['payload_json']).get('revision_id')
        if not isinstance(revision,str):revision=None
        named=db.execute('SELECT r.original_filename FROM documents d JOIN file_revisions r '
                         'ON r.document_id=d.id AND r.id=COALESCE(?,d.current_revision_id) WHERE d.id=?',
                         (revision,job['target_id'])).fetchone()
        if named:
            result['document_name']=named[0].replace('\\','/').rsplit('/',1)[-1]
    return result
