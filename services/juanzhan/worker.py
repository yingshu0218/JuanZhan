"""One worker process, one isolated handler child at a time.

Handlers are at-least-once. Database handlers must use fenced JobQueue.complete effects;
remote requests need their own stable idempotency keys. Never claim exactly-once I/O.
"""
import argparse
import json
import logging
import multiprocessing
from pathlib import Path
import signal
import socket
import threading
import time

from .config import Settings
from .database import migrate
from .jobs import JobQueue, LostLease, encoded
from .storage import ManagedStore, StorageBusy

logger = logging.getLogger('juanzhan.worker')



def _send(connection,message):
    # Shutdown may close the parent's result pipe before the child finishes.
    # Durable completion/leases, rather than this acknowledgement, own job state.
    try:connection.send(message)
    except (OSError,EOFError):pass


def _handler(job,data_dir,connection,source_mounts=(),converter_token=''):
    try:
        if job['kind']=='reindex' and job['target_type']=='document_search':
            import resource
            resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
            resource.setrlimit(resource.RLIMIT_CPU,(60,60))
            from .indexing import execute,IndexFailure
            try:
                execute(Settings(data_dir=Path(data_dir),converter_token=''),job)
                _send(connection,('committed',))
            except IndexFailure as exc:
                _send(connection,('failure',exc.code,'Index could not be refreshed safely',False))
            return
        if job['kind'] in ('parse','ocr') and job['target_type']=='document':
            from .parsing import execute,ParseFailure
            settings=Settings(data_dir=Path(data_dir),converter_token=converter_token,source_mounts=source_mounts)
            try:
                execute(settings,job)
                _send(connection,('committed',))
            except ParseFailure as exc:
                _send(connection,('failure',exc.code,'Parse attempt could not complete safely',exc.retryable))
            return
        if job['kind']=='gc' and job['target_type']=='derived_objects':
            from .derived import run_gc
            run_gc(Settings(data_dir=Path(data_dir),converter_token=''),job)
            _send(connection,('committed',))
            return
        if job['target_type'] in ('source_exclude','document_purge','managed_objects') and job['kind'] in ('batch','purge','gc'):
            from .maintenance import exclude,purge,run_gc
            from fastapi import HTTPException
            settings=Settings(data_dir=Path(data_dir),converter_token='')
            try:
                if job['target_type']=='managed_objects':run_gc(settings,job)
                else:
                    callback=exclude if job['target_type']=='source_exclude' else lambda db,owned:purge(db,owned,settings)
                    JobQueue(settings).complete(job['id'],job['lease_token'],callback)
                _send(connection, ('committed',))
            except HTTPException as exc:
                _send(connection, ('failure',exc.detail['code'],'Maintenance request is no longer applicable',False))
            return
        if job['kind']=='scan' and job['target_type'] in ('source_initial','source_incremental'):
            from .source_initial import initial
            from .source_paths import SourcePathError
            settings = Settings(data_dir=Path(data_dir),converter_token='',source_mounts=source_mounts)
            try:
                if job['target_type']=='source_initial':
                    initial(settings,job)
                else:
                    from .source_incremental import incremental
                    incremental(settings,job)
                _send(connection, ('committed',))
            except SourcePathError as exc:
                _send(connection, ('failure',exc.code,'Source scan could not complete safely',
                    exc.code in ('SOURCE_OFFLINE','SOURCE_CHANGED','SOURCE_FILE_MISSING')))
            return
        if job['kind']=='scan_preview' and job['target_type']=='source_preview':
            from .source_scans import preview
            from .source_paths import SourcePathError
            settings = Settings(data_dir=Path(data_dir),converter_token='',source_mounts=source_mounts)
            try:
                result = preview(settings,job)
                encoded(result)
                _send(connection, ('success',result))
            except SourcePathError as exc:
                _send(connection, ('failure',exc.code,'Source preview could not complete safely',
                    exc.code in ('SOURCE_OFFLINE','SOURCE_CHANGED','SOURCE_FILE_MISSING')))
            return
        if job['kind']=='batch' and job['target_type'] in ('document_batch','document_batch_undo'):
            from .batches import execute
            settings = Settings(data_dir=Path(data_dir),converter_token='')
            JobQueue(settings).complete(job['id'],job['lease_token'],execute)
            _send(connection, ('committed',))
            return
        if job['kind']!='gc' or job['target_type']!='managed_staging':
            _send(connection, ('failure','HANDLER_NOT_AVAILABLE','Job handler is not implemented',False))
            return
        payload = json.loads(job['payload_json'])
        if set(payload)-{'minimum_age_seconds'}:
            _send(connection, ('failure','INVALID_JOB_PAYLOAD','Unsupported maintenance parameters',False))
            return
        age = payload.get('minimum_age_seconds',3600)
        if isinstance(age,bool) or not isinstance(age,(int,float)) or not 0<=age<=31536000:
            _send(connection, ('failure','INVALID_JOB_PAYLOAD','Invalid recovery age',False))
            return
        store = ManagedStore(Path(data_dir)/'managed')
        removed = store.recover_staging(minimum_age_seconds=age)
        result = {'removed_staging_files':removed}
        encoded(result)
        _send(connection, ('success',result))
    except StorageBusy:
        _send(connection, ('failure','STORAGE_BUSY','Storage recovery deferred while writers are active',True))
    except OSError:
        _send(connection, ('failure','STORAGE_IO_ERROR','Storage maintenance encountered an I/O error',True))
    except Exception:
        # Never persist raw exception text, stack traces, paths or job inputs.
        _send(connection, ('failure','HANDLER_ERROR','Job handler failed',False))
    finally:
        connection.close()


class Worker:
    def __init__(self,settings,*,owner=None,lease_seconds=30,stop=None,handler=None):
        if not 0<lease_seconds<=300:
            raise ValueError('Invalid lease duration')
        self.settings = settings
        self.queue = JobQueue(settings)
        self.owner = owner or socket.gethostname()
        self.lease_seconds = lease_seconds
        self.stop = stop or threading.Event()
        self.handler = handler or _handler

    @staticmethod
    def terminate(process):
        if process.is_alive():
            process.terminate()
            process.join(timeout=0.5)
        if process.is_alive():
            process.kill()
            process.join(timeout=0.5)
        else:
            process.join(timeout=0.5)

    def run_once(self,*,prefer_index=False):
        self.queue.worker_heartbeat(self.owner)
        job = self.queue.claim(self.owner,lease_seconds=self.lease_seconds,prefer_index=prefer_index)
        if job is None:
            return None
        context = multiprocessing.get_context('spawn')
        receive,send = context.Pipe(duplex=False)
        arguments = (job,str(self.settings.data_dir),send)
        if self.handler is _handler:
            arguments += (self.settings.source_mounts,self.settings.converter_token)
        process = context.Process(target=self.handler,args=arguments,daemon=True)
        started = time.monotonic()
        next_heartbeat = started
        outcome = None
        try:
            process.start()
            send.close()
            while True:
                if self.stop.is_set():
                    outcome = ('failure','WORKER_STOPPED','Worker is shutting down',True)
                    break
                if time.monotonic()-started>=job['timeout_seconds']:
                    outcome = ('failure','JOB_TIMEOUT','Job execution deadline exceeded',True)
                    break
                if time.monotonic()>=next_heartbeat:
                    self.queue.heartbeat(job['id'],job['lease_token'],lease_seconds=self.lease_seconds)
                    self.queue.worker_heartbeat(self.owner)
                    next_heartbeat = time.monotonic()+min(self.lease_seconds/3,2)
                if receive.poll(0.02):
                    try:
                        outcome = receive.recv()
                    except EOFError:
                        outcome = ('failure','WORKER_CHILD_EXITED','Handler process exited without a result',True)
                    break
                if not process.is_alive():
                    outcome = ('failure','WORKER_CHILD_EXITED','Handler process exited without a result',True)
                    break
            self.terminate(process)
            if outcome[0]=='committed':
                pass  # Handler committed fenced database effects and completion together.
            elif outcome[0]=='success':
                self.queue.complete(job['id'],job['lease_token'],outcome[1])
            else:
                self.queue.failure(job['id'],job['lease_token'],outcome[1],outcome[2],retryable=outcome[3])
        except LostLease:
            logger.warning('Job %s lease lost; result discarded',job['id'])
        except Exception:
            # A process launch/IPC/DB failure leaves the lease for bounded recovery.
            logger.error('Worker infrastructure failure for job %s; lease will recover',job['id'])
        finally:
            if process.pid is not None:
                self.terminate(process)
                process.close()
            receive.close()
            send.close()
        status = self.queue.get(job['id'])['status']
        logger.info('Job %s attempt %d is %s',job['id'],job['attempts'],status)
        return {'job_id':job['id'],'status':status}


def main():
    parser = argparse.ArgumentParser(description='Run durable Archive worker')
    parser.add_argument('--once',action='store_true',help='Run at most one attempt; inspect Job state for its outcome')
    parser.add_argument('--healthcheck',action='store_true')
    parser.add_argument('--poll-seconds',type=float,default=1)
    args = parser.parse_args()
    if not 0.05<=args.poll_seconds<=5:
        parser.error('Poll interval must be between 0.05 and 5 seconds')
    settings = Settings.from_env()
    owner = socket.gethostname()
    queue = JobQueue(settings)
    if args.healthcheck:
        try:
            healthy = queue.worker_healthy(owner)
        except Exception:
            healthy = False
        raise SystemExit(0 if healthy else 1)
    settings.prepare_archive()
    migrate(settings.database)
    ManagedStore(settings.data_dir/'managed').initialize()
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    stop = threading.Event()
    for name in (signal.SIGTERM,signal.SIGINT):
        signal.signal(name,lambda *_:stop.set())
    worker = Worker(settings,owner=owner,stop=stop)
    if args.once:
        print(json.dumps(worker.run_once()))
        return
    prefer_index=False
    while not stop.is_set():
        try:
            from .indexing import schedule
            schedule(settings,limit=1)
            worker.run_once(prefer_index=prefer_index)
            prefer_index=not prefer_index
        except Exception:
            logger.error('Queue unavailable; retrying after bounded poll interval')
        stop.wait(args.poll_seconds)


if __name__=='__main__':
    main()
