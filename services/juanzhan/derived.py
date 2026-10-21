"""Reference-aware derived object recovery; never accesses original/source volumes."""
import os
import re
import stat
import time

from .jobs import JobQueue,JobSpec
from .storage import ManagedStore,directory,parse_key

RETENTION=86400

def schedule_gc(db,settings,key,due):
    job=JobQueue(settings).enqueue(JobSpec(kind='gc',target_type='derived_objects',idempotency_key=key,timeout_seconds=120),db=db)
    db.execute("UPDATE jobs SET available_at=? WHERE id=? AND status='queued'",(due,job['id']))
    return job


def collect(db,job,root,settings,clock=time.time):
    now=clock();counts={'discovered':0,'deleted_objects':0,'retained_objects':0,'ignored_files':0}
    with directory(root,'sha256') as objects:
        for prefix in os.listdir(objects):
            if not re.fullmatch('[0-9a-f]{2}',prefix):continue
            try:
                with directory(objects,prefix) as bucket:
                    for name in os.listdir(bucket):
                        key='sha256/'+prefix+'/'+name
                        try:_,size=parse_key(key)
                        except ValueError:counts['ignored_files']+=1;continue
                        info=os.stat(name,dir_fd=bucket,follow_symlinks=False)
                        if not stat.S_ISREG(info.st_mode) or info.st_size!=size:
                            counts['ignored_files']+=1;continue
                        if db.execute('SELECT 1 FROM derived_object_references WHERE storage_key=? LIMIT 1',(key,)).fetchone():
                            db.execute('DELETE FROM derived_gc_candidates WHERE storage_key=?',(key,))
                            counts['retained_objects']+=1;continue
                        candidate=db.execute('SELECT eligible_after FROM derived_gc_candidates WHERE storage_key=?',(key,)).fetchone()
                        if candidate is None:
                            db.execute('INSERT INTO derived_gc_candidates VALUES (?,?)',(key,now+RETENTION))
                            counts['discovered']+=1;continue
                        if candidate[0]>now:counts['retained_objects']+=1;continue
                        os.unlink(name,dir_fd=bucket);os.fsync(bucket)
                        db.execute('DELETE FROM derived_gc_candidates WHERE storage_key=?',(key,))
                        counts['deleted_objects']+=1
            except (NotADirectoryError,FileNotFoundError):continue
            except OSError as exc:
                if exc.errno==40:counts['ignored_files']+=1
                else:raise
    for key, in db.execute('SELECT storage_key FROM derived_gc_candidates WHERE eligible_after<=?',(now,)).fetchall():
        try:parse_key(key)
        except ValueError:continue
        if not db.execute('SELECT 1 FROM derived_object_references WHERE storage_key=?',(key,)).fetchone() and ManagedStore(settings.data_dir/'derived').probe(key)=='missing':
            db.execute('DELETE FROM derived_gc_candidates WHERE storage_key=?',(key,))
    future=db.execute('SELECT min(eligible_after) FROM derived_gc_candidates').fetchone()[0]
    if future is not None:schedule_gc(db,settings,'derived-followup:'+job['id'],max(now,future))
    return counts


def run_gc(settings,job):
    store=ManagedStore(settings.data_dir/'derived');store.initialize()
    store.recover_staging(minimum_age_seconds=3600)
    with store.locked(exclusive=True) as root:
        JobQueue(settings).complete(job['id'],job['lease_token'],lambda db,owned:collect(db,owned,root,settings))
