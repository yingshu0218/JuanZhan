"""Operator-only recovery activation staging and private artifact cleanup.

HTTP never accepts these filesystem destinations or exposes absolute paths.
This tool refuses existing output directories and never switches a live instance.
"""
import argparse
import json
from pathlib import Path
import shutil
import sqlite3
import uuid

from fastapi import HTTPException

from . import backup
from .backup_management import Repository, cleanup
from .config import Settings
from .database import connect
from .jobs import JobQueue
from .storage import StorageError, StorageBusy


def recovery(settings, repository, id):
    with connect(settings.database) as db:
        row=db.execute("SELECT r.artifact_token,j.status FROM recovery_records r JOIN jobs j ON j.id=r.job_id WHERE r.id=?",(id,)).fetchone()
    if row is None or row[0] is None or row[1]!='completed':
        raise ValueError('Recovery is not ready')
    path=repository.path('recoveries',id,row[0])
    if path.is_symlink() or not path.is_dir() or (path/'RESTORE_IN_PROGRESS').exists():
        raise ValueError('Recovery data is unavailable')
    return path


def stage(settings, id, destination):
    repository=Repository(settings)
    destination=Path(destination).resolve()
    for protected in [settings.data_dir.resolve(),repository.root.resolve(),*(Path(path).resolve() for _,path in settings.source_mounts)]:
        if destination.is_relative_to(protected) or protected.is_relative_to(destination):
            raise ValueError('Recovery output must be separate from existing data')
    with repository.locked():
        source=recovery(settings,repository,id)
        work=repository.path('work',uuid.uuid4().hex,uuid.uuid4().hex)
        work.mkdir(mode=0o700)
        try:
            backup.create(Settings(source,''),work/'bundle')
            result=backup.restore(work/'bundle',destination)
            return {**result,'recovery_id':id,'data_dir':str(destination),'activation_required':True}
        finally:
            shutil.rmtree(work,ignore_errors=True)


def remove(settings, id):
    repository=Repository(settings)
    with repository.locked():
        path=recovery(settings,repository,id)
        live=settings.data_dir.resolve()
        if live.is_relative_to(path.resolve()) or path.resolve().is_relative_to(live):
            raise ValueError('Cannot remove active data')
        with JobQueue(settings).write() as db:
            db.execute('UPDATE recovery_records SET artifact_token=NULL WHERE id=?',(id,))
        shutil.rmtree(path)
        backup.sync_directory(path.parent)
    return {'recovery_id':id,'removed':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    locate=commands.add_parser('locate-recovery');locate.add_argument('--id',required=True)
    staging=commands.add_parser('stage-recovery');staging.add_argument('--id',required=True);staging.add_argument('--output',type=Path,required=True)
    deletion=commands.add_parser('remove-recovery');deletion.add_argument('--id',required=True);deletion.add_argument('--confirm',action='store_true',required=True)
    commands.add_parser('cleanup-orphans')
    args=parser.parse_args()
    try:
        settings=Settings.from_env()
        if args.command=='stage-recovery':result=stage(settings,args.id,args.output)
        elif args.command=='remove-recovery':result=remove(settings,args.id)
        else:
            repository=Repository(settings)
            with repository.locked():
                if args.command=='locate-recovery':result={'recovery_id':args.id,'data_dir':str(recovery(settings,repository,args.id)),'activation_required':True}
                else:result={'removed':cleanup(settings,repository)}
    except (OSError,ValueError,RuntimeError,StorageError,StorageBusy,HTTPException,sqlite3.Error):
        parser.exit(1,'Recovery administration failed; inspect the selected ID, private storage and application version.\n')
    print(json.dumps(result))

if __name__=='__main__':main()
