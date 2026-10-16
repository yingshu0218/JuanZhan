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


def _handler(job,data_dir,connection):
    try:
        if job['kind']!='gc' or job['target_type']!='managed_staging':
            connection.send(('failure','HANDLER_NOT_AVAILABLE','Job handler is not implemented',False))
            return
        payload = json.loads(job['payload_json'])
        if set(payload)-{'minimum_age_seconds'}:
            connection.send(('failure','INVALID_JOB_PAYLOAD','Unsupported maintenance parameters',False))
            return
        age = payload.get('minimum_age_seconds',3600)
        if isinstance(age,bool) or not isinstance(age,(int,float)) or not 0<=age<=31536000:
            connection.send(('failure','INVALID_JOB_PAYLOAD','Invalid recovery age',False))
            return
        store = ManagedStore(Path(data_dir)/'managed')
        removed = store.recover_staging(minimum_age_seconds=age)
        result = {'removed_staging_files':removed}
        encoded(result)
        connection.send(('success',result))
    except StorageBusy:
        connection.send(('failure','STORAGE_BUSY','Storage recovery deferred while writers are active',True))
    except OSError:
        connection.send(('failure','STORAGE_IO_ERROR','Storage maintenance encountered an I/O error',True))
    except Exception:
        # Never persist raw exception text, stack traces, paths or job inputs.
        connection.send(('failure','HANDLER_ERROR','Job handler failed',False))
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

    def run_once(self):
        self.queue.worker_heartbeat(self.owner)
        job = self.queue.claim(self.owner,lease_seconds=self.lease_seconds)
        if job is None:
            return None
        context = multiprocessing.get_context('spawn')
        receive,send = context.Pipe(duplex=False)
        process = context.Process(target=self.handler,args=(job,str(self.settings.data_dir),send),daemon=True)
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
            if outcome[0]=='success':
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
    while not stop.is_set():
        try:
            worker.run_once()
        except Exception:
            logger.error('Queue unavailable; retrying after bounded poll interval')
        stop.wait(args.poll_seconds)


if __name__=='__main__':
    main()
