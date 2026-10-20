"""Bounded multipart ingestion. Preserve originals; never execute or extract them."""
import asyncio
import codecs
from pathlib import Path
import re
import struct
import zipfile
import zlib

from fastapi import APIRouter, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser, parse_options_header
from starlette.requests import ClientDisconnect
from python_multipart.exceptions import MultipartParseError

from .auth import fail
from .catalog import required, same_space, transaction
from .documents import Registration
from .jobs import JobSpec
from .storage import IntegrityError, SizeLimitExceeded


class BoundedParser(MultiPartParser):
    spool_max_size = 64 * 1024

    def __init__(self,*args,max_bytes,**kwargs):
        super().__init__(*args,**kwargs)
        self.max_bytes = max_bytes
        self.file_bytes = 0
        self.ended = False
        self.too_large = False
        self.header_bytes = 0

    def on_part_begin(self):
        super().on_part_begin()
        self.file_bytes = 0
        self.header_bytes = 0

    def on_part_data(self,data,start,end):
        if self._current_part.file is not None:
            self.file_bytes += end-start
            if self.file_bytes>self.max_bytes:
                self.too_large = True
                raise MultiPartException('File too large')
        super().on_part_data(data,start,end)

    def header_limit(self,start,end):
        self.header_bytes += end-start
        if self.header_bytes>8192:
            raise MultiPartException('Part headers too large')

    def on_header_field(self,data,start,end):
        self.header_limit(start,end)
        super().on_header_field(data,start,end)

    def on_header_value(self,data,start,end):
        self.header_limit(start,end)
        super().on_header_value(data,start,end)

    def on_end(self):
        self.ended = True


def sniff(file,filename):
    file.seek(0)
    head = file.read(65536)
    file.seek(0)
    if head.startswith(b'%PDF-'):return 'application/pdf'
    for signature,mime in ((b'\x89PNG\r\n\x1a\n','image/png'),(b'\xff\xd8\xff','image/jpeg'),
                           (b'GIF87a','image/gif'),(b'GIF89a','image/gif'),
                           (b'II*\x00','image/tiff'),(b'MM\x00*','image/tiff')):
        if head.startswith(signature):return mime
    if head.startswith(b'PK\x03\x04'):
        try:
            # Bound central-directory work before ZipFile reads it. Never extract entries.
            file.seek(0,2)
            end=file.tell()
            file.seek(max(0,end-65557))
            tail=file.read(65557)
            pos=tail.rfind(b'PK\x05\x06')
            if pos<0 or len(tail)-pos<22 or b'PK\x06\x07' in tail or b'PK\x06\x06' in tail: return 'application/zip'
            info=struct.unpack_from('<4s4H2LH',tail,pos)
            if info[1] or info[2] or info[4]>1024 or info[5]>1024*1024:return 'application/zip'
            file.seek(0)
            with zipfile.ZipFile(file) as archive:
                names=set(archive.namelist())
                if {'[Content_Types].xml','word/document.xml'}<=names:
                    return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                if 'mimetype' in names:
                    entry=archive.getinfo('mimetype')
                    if entry.file_size<=64 and entry.compress_size<=128 and not entry.flag_bits&1:
                        if archive.read(entry)==b'application/epub+zip':return 'application/epub+zip'
        except (ValueError,OSError,zipfile.BadZipFile,RuntimeError,NotImplementedError,zlib.error,EOFError,struct.error,OverflowError):
            pass
        finally:
            file.seek(0)
        return 'application/zip'
    if head.lstrip().startswith(b'{\\rtf'):return 'application/rtf'
    if not head:return 'application/octet-stream'
    try:
        encoding='utf-32' if head.startswith((b'\xff\xfe\x00\x00',b'\x00\x00\xfe\xff')) else 'utf-16' if head.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig'
        text=codecs.getincrementaldecoder(encoding)().decode(head,final=False)
        if any(ord(c)<32 and c not in '\t\n\r\f' for c in text):return 'application/octet-stream'
        if re.search(r'<(?:!doctype\s+html|html|head|body)(?:\s|>)',text[:4096],re.I):return 'text/html'
        return 'text/markdown' if Path(filename).suffix.lower() in ('.md','.markdown') else 'text/plain'
    except UnicodeDecodeError:
        return 'application/octet-stream'


def router(settings):
    routes=APIRouter(prefix='/api/v1/documents')
    slots=asyncio.Semaphore(2)

    @routes.post('/upload',status_code=201)
    async def upload(request: Request):
        content_type,options=parse_options_header(request.headers.get('content-type',''))
        if content_type!=b'multipart/form-data' or not 1<=len(options.get(b'boundary',b''))<=200:
            fail(400,'INVALID_MULTIPART','Valid multipart boundary required')
        limit=settings.upload_max_bytes+65536
        try:
            declared=int(request.headers['content-length']) if 'content-length' in request.headers else None
        except ValueError:
            fail(400,'INVALID_MULTIPART','Invalid request length')
        if declared is not None and (declared<0 or declared>limit):
            fail(413,'UPLOAD_TOO_LARGE','Request exceeds the configured limit')
        # Do not queue unbounded waiting uploads or consume their bodies.
        if slots.locked():fail(429,'UPLOAD_CAPACITY','Upload capacity reached; retry later')
        async with slots:
            total=0
            parser=None
            form=None
            async def bounded_stream():
                nonlocal total
                async for chunk in request.stream():
                    total+=len(chunk)
                    if total>limit:
                        parser.too_large=True
                        raise MultiPartException('Request too large')
                    for offset in range(0,len(chunk),65536):
                        yield chunk[offset:offset+65536]
            parser=BoundedParser(request.headers,bounded_stream(),max_files=1,max_fields=4,
                                 max_part_size=4096,max_bytes=settings.upload_max_bytes)
            try:
                try:
                    async with asyncio.timeout(settings.upload_timeout_seconds):
                        form=await parser.parse()
                    if not parser.ended:fail(400,'INVALID_MULTIPART','Incomplete multipart body')
                except (MultiPartException,MultipartParseError):
                    if parser.too_large:fail(413,'UPLOAD_TOO_LARGE','File or request exceeds configured limit')
                    fail(400,'INVALID_MULTIPART','Invalid or excessive multipart fields')
                except TimeoutError:
                    fail(408,'UPLOAD_TIMEOUT','Upload receive deadline exceeded')
                except ClientDisconnect:
                    fail(400,'UPLOAD_INTERRUPTED','Upload stream interrupted')
                pairs=form.multi_items()
                if len({name for name,_ in pairs})!=len(pairs) or set(form)-{'file','space_id','folder_id','triage_status','duplicate_policy'}:
                    fail(422,'INVALID_REQUEST','Unexpected or repeated form fields')
                file=form.get('file')
                if not isinstance(file,UploadFile) or any(isinstance(value,UploadFile) for name,value in pairs if name!='file'):
                    fail(422,'INVALID_REQUEST','Exactly one file field required')
                metadata={name:value for name,value in pairs if name!='file'}
                try:
                    info=Registration(original_filename=file.filename or '',title=file.filename or '',
                                      mime_type='application/octet-stream',**metadata)
                except (ValidationError,TypeError):
                    fail(422,'INVALID_REQUEST','Invalid upload metadata')
                def save():
                    with transaction(settings) as db:
                        required(db,'spaces',info.space_id)
                        if info.folder_id is not None:
                            same_space(db,'folders',info.folder_id,info.space_id)
                    # Hash/file checks happen off the event loop. No decompression or parsing.
                    mime=sniff(file.file,info.original_filename)
                    file.file.seek(0)
                    obj=request.app.state.storage.put(file.file,max_bytes=settings.upload_max_bytes,
                                                       expected_size=file.size)
                    info_with_mime=info.model_copy(update={'mime_type':mime})
                    result={}
                    def enqueue(db,document):
                        job=request.app.state.jobs.enqueue(JobSpec(kind='parse',target_type='document',
                            target_id=document['id'],idempotency_key='parse:'+document['current_revision_id'],
                            payload={'revision_id':document['current_revision_id']}),db=db)
                        result['job_id']=job['id']
                    document=request.app.state.documents.register_managed(obj,info_with_mime,
                                                                          request=request,after_create=enqueue)
                    return {'document_id':document['id'],'revision_id':document['current_revision_id'],
                            'job_id':result['job_id'],'upload_status':'saved'}
                try:
                    return await run_in_threadpool(save)
                except SizeLimitExceeded:
                    fail(413,'UPLOAD_TOO_LARGE','File exceeds the configured limit')
                except IntegrityError:
                    fail(409,'STORAGE_INTEGRITY_ERROR','Stored original failed integrity verification')
                except OSError:
                    fail(503,'STORAGE_UNAVAILABLE','Original could not be safely stored')
            finally:
                # Also close files when timeout/disconnect bypasses Starlette's parse cleanup.
                for file in parser._files_to_close_on_error:
                    file.close()
                if form is not None:await form.close()
    return routes
