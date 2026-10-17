"""Source configuration and read-only inventory queries. Never accepts disk roots."""
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import Field

from .auth import authorize, fail
from .catalog import Input, ID, Name, now, required, same_space, scope, transaction
from .jobs import JobQueue, JobSpec
from .source_paths import SourceMounts, SourcePathError, components


class ScanRequest(Input):
    mode: Literal['initial', 'incremental']


class SourceCreate(Input):
    space_id: ID
    name: Name
    kind: Literal['external']
    root_alias: Annotated[str, Field(pattern=r'^[a-z][a-z0-9_-]{0,63}$')]
    initial_import_policy: Literal['tree', 'flat']
    initial_target_folder_id: ID | None = None
    initial_triage_status: Literal['filed', 'needs_review'] = 'filed'
    new_file_target_folder_id: ID | None = None
    scan_interval_minutes: Annotated[int, Field(strict=True, ge=0, le=525600)] | None = None


def health(mounts, alias):
    try:
        with mounts.root(alias):
            pass
        return {'mount_status': 'ready', 'error_code': None}
    except SourcePathError as exc:
        return {'mount_status': 'offline' if exc.code == 'SOURCE_OFFLINE' else 'unavailable',
                'error_code': exc.code}


def public(db, mounts, source):
    result = {k: source[k] for k in ('id', 'space_id', 'name', 'kind', 'status', 'initial_import_policy',
        'initial_target_folder_id', 'initial_triage_status', 'initial_import_completed_at',
        'new_file_target_folder_id', 'scan_interval_minutes', 'last_successful_scan_at')}
    result['root_alias'] = source['root_ref']
    result['health'] = health(mounts, source['root_ref'])
    if source['status'] != 'disabled':
        if result['health']['mount_status'] != 'ready':
            result['status'] = 'offline' if result['health']['mount_status'] == 'offline' else 'error'
        elif db.execute("SELECT 1 FROM scan_runs r JOIN jobs j ON j.target_id=r.id "
                        "WHERE r.source_id=? AND j.target_type IN ('source_preview','source_initial','source_incremental') AND j.status IN ('queued','running')",
                        (source['id'],)).fetchone():
            result['status'] = 'scanning'
        else:
            result['status'] = 'error' if source['status'] == 'error' else 'ready'
    return result


def router(settings):
    result = APIRouter(prefix='/api/v1')
    mounts = SourceMounts(settings.source_mounts)
    queue = JobQueue(settings)

    @result.get('/source-mounts')
    def configured_mounts(request: Request):
        authorize(settings, request)
        return JSONResponse({'items': mounts.list()}, headers={'Cache-Control': 'no-store'})

    @result.get('/sources')
    def sources(space_id: ID | None = None):
        with transaction(settings) as db:
            scope(db, space_id)
            return [public(db, mounts, s) for s in db.execute(
                'SELECT * FROM sources WHERE (? IS NULL OR space_id=?) ORDER BY created_at,id', (space_id, space_id))]

    @result.post('/sources', status_code=201)
    def create(body: SourceCreate, request: Request):
        with transaction(settings, request) as db:
            required(db, 'spaces', body.space_id)
            for folder in (body.initial_target_folder_id, body.new_file_target_folder_id):
                if folder is not None:
                    same_space(db, 'folders', folder, body.space_id)
            try:
                identity = mounts.identity(body.root_alias)
                for old in db.execute("SELECT root_ref FROM sources WHERE kind='external'"):
                    # Same alias remains reserved even while its mount is offline.
                    if old['root_ref'] == body.root_alias:
                        fail(409, 'SOURCE_OVERLAP', 'Source mount is already registered')
                    try:
                        other = mounts.identity(old['root_ref'])
                    except SourcePathError:
                        # Cannot prove separation from an unavailable configured source.
                        fail(409, 'SOURCE_OVERLAP_UNVERIFIED', 'Existing source mount must be available to verify separation')
                    if mounts.overlaps(identity, other):
                        fail(409, 'SOURCE_OVERLAP', 'Source roots overlap')
            except SourcePathError as exc:
                fail(422, exc.code, 'An approved readable read-only mount is required')
            id, timestamp = uuid.uuid4().hex, now()
            db.execute('INSERT INTO sources(id,space_id,name,kind,root_ref,status,initial_import_policy,'
                'initial_target_folder_id,initial_triage_status,new_file_target_folder_id,scan_interval_minutes,created_at,updated_at) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (id, body.space_id, body.name, body.kind, body.root_alias, 'ready', body.initial_import_policy,
                 body.initial_target_folder_id, body.initial_triage_status, body.new_file_target_folder_id,
                 body.scan_interval_minutes, timestamp, timestamp))
            return public(db, mounts, required(db, 'sources', id))

    @result.get('/sources/{id}')
    def source(id: str):
        with transaction(settings) as db:
            return public(db, mounts, required(db, 'sources', id))

    @result.get('/sources/{id}/entries')
    def entries(id: str, relative_prefix: str | None = None,
                page: Annotated[int, Query(ge=1, le=1000000)] = 1,
                page_size: Annotated[int, Query(ge=1, le=100)] = 30):
        if relative_prefix is not None:
            try:
                components(relative_prefix)
            except SourcePathError:
                fail(422, 'INVALID_SOURCE_PATH', 'A canonical relative prefix is required')
        with transaction(settings) as db:
            required(db, 'sources', id)
            # Prefix is a complete directory segment, not SQL LIKE (%, _ remain literal).
            condition = 'source_id=? AND (? IS NULL OR relative_path_norm=? OR substr(relative_path_norm,1,length(?)+1)=?||\'/\')'
            params = (id, relative_prefix, relative_prefix, relative_prefix, relative_prefix)
            total = db.execute('SELECT count(*) FROM source_entries WHERE ' + condition, params).fetchone()[0]
            rows = db.execute('SELECT id,source_id,document_id,relative_path_display AS relative_path,size_bytes,status,sha256 '
                'FROM source_entries WHERE ' + condition + ' ORDER BY relative_path_norm,id LIMIT ? OFFSET ?',
                (*params, page_size, (page-1)*page_size)).fetchall()
            return {'items': [dict(r) for r in rows], 'page': page, 'page_size': page_size, 'total': total}

    @result.post('/sources/{id}/preview-scan', status_code=202)
    def preview(id: str, request: Request):
        with transaction(settings, request) as db:
            source = required(db, 'sources', id)
            if source['kind'] != 'external' or source['status'] == 'disabled':
                fail(409, 'SOURCE_DISABLED', 'Source cannot be scanned')
            active = db.execute("SELECT j.id,j.status,j.target_type FROM scan_runs r JOIN jobs j ON j.target_id=r.id "
                "WHERE r.source_id=? AND j.target_type IN ('source_preview','source_initial','source_incremental') AND j.status IN ('queued','running') ORDER BY j.created_at,j.id LIMIT 1", (id,)).fetchone()
            if active:
                if active['target_type'] != 'source_preview':
                    fail(409, 'SOURCE_SCAN_BUSY', 'Another source scan is active')
                return {'job_id': active['id'], 'status': active['status']}
            probe = health(mounts, source['root_ref'])
            if probe['mount_status'] != 'ready':
                fail(422, probe['error_code'], 'A readable read-only mount is required')
            run_id, timestamp = uuid.uuid4().hex, now()
            db.execute("INSERT INTO scan_runs(id,source_id,mode,status,created_at) VALUES (?,?,'preview','queued',?)", (run_id, id, timestamp))
            job = queue.enqueue(JobSpec(kind='scan_preview', target_type='source_preview', target_id=run_id,
                payload={}, idempotency_key='source-preview:'+run_id, timeout_seconds=120), db=db)
            return {'job_id': job['id'], 'status': job['status']}

    @result.post('/sources/{id}/scan', status_code=202)
    def scan(id: str, body: ScanRequest, request: Request):
        with transaction(settings, request) as db:
            source = required(db, 'sources', id)
            if source['kind'] != 'external' or source['status'] == 'disabled':
                fail(409, 'SOURCE_DISABLED', 'Source cannot be scanned')
            if body.mode == 'incremental' and source['initial_import_completed_at'] is None:
                fail(409, 'SOURCE_INITIAL_REQUIRED', 'Complete the initial import first')
            if body.mode == 'initial' and source['initial_import_completed_at'] is not None:
                completed = db.execute("SELECT j.id,j.status FROM scan_runs r JOIN jobs j ON j.target_id=r.id "
                    "WHERE r.source_id=? AND j.target_type='source_initial' AND j.status='completed' ORDER BY j.created_at,j.id LIMIT 1",
                    (id,)).fetchone()
                if completed:
                    return {'job_id': completed['id'], 'status': completed['status']}
                fail(409, 'SOURCE_INITIAL_ALREADY_COMPLETED', 'Initial import was already completed')
            active = db.execute("SELECT j.id,j.status,j.target_type FROM scan_runs r JOIN jobs j ON j.target_id=r.id "
                "WHERE r.source_id=? AND j.target_type IN ('source_preview','source_initial','source_incremental') AND j.status IN ('queued','running') "
                "ORDER BY j.created_at,j.id LIMIT 1", (id,)).fetchone()
            if active:
                if active['target_type'] != 'source_'+body.mode:
                    fail(409, 'SOURCE_SCAN_BUSY', 'Another source scan is active')
                return {'job_id': active['id'], 'status': active['status']}
            probe = health(mounts, source['root_ref'])
            if probe['mount_status'] != 'ready':
                fail(422, probe['error_code'], 'A readable read-only mount is required')
            run_id, timestamp = uuid.uuid4().hex, now()
            db.execute("INSERT INTO scan_runs(id,source_id,mode,status,created_at) VALUES (?,?,?,'queued',?)", (run_id,id,body.mode,timestamp))
            job = queue.enqueue(JobSpec(kind='scan', target_type='source_'+body.mode, target_id=run_id,
                payload={}, idempotency_key='source-'+body.mode+':'+run_id, timeout_seconds=300), db=db)
            return {'job_id': job['id'], 'status': job['status']}

    return result
