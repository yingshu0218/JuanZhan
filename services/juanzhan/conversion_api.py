"""Authenticated, bounded multipart and controlled artifact transport."""
import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import ValidationError
from python_multipart.exceptions import MultipartParseError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, parse_options_header
from starlette.requests import ClientDisconnect

from .auth import fail
from .conversion_models import Options
from .uploads import BoundedParser


def router(store):
    routes = APIRouter(prefix='/v1')
    receiving = asyncio.Semaphore(1)
    config = store.config
    from .conversion_formats import SUPPORTED
    from .conversion_raster import IMAGES, available_languages
    languages_available=available_languages(config.ocr_models_dir) if config.enable_ocr else ()

    @routes.get('/capabilities')
    def capabilities():
        return {'schema_versions': ['1.0'], 'supported_input_types': SUPPORTED+IMAGES,
                'ocr_available': bool(languages_available), 'max_file_bytes': config.max_file_bytes,
                'max_pages': config.max_pages, 'preview_available': True, 'ocr_languages': list(languages_available),
                'preview_input_types': ['application/pdf']+IMAGES,
                'preview_kind': 'thumbnail', 'max_preview_pages': config.max_preview_pages,
                'max_ocr_pages': config.max_ocr_pages, 'max_image_pixels': config.max_image_pixels,
                'render_dpi': config.render_dpi,
                'max_output_bytes': config.max_output_bytes, 'max_blocks': config.max_blocks,
                'max_jobs': config.max_jobs, 'ttl_seconds': config.ttl_seconds,
                'wall_seconds': config.wall_seconds, 'cpu_seconds': config.cpu_seconds,
                'memory_bytes': config.memory_bytes,
                'max_archive_entries': config.max_archive_entries, 'max_archive_bytes': config.max_archive_bytes,
                'max_archive_member_bytes': config.max_archive_member_bytes,
                'max_compression_ratio': config.max_compression_ratio}

    @routes.post('/jobs', status_code=202)
    async def submit(request: Request):
        content_type, options = parse_options_header(request.headers.get('content-type',''))
        if content_type != b'multipart/form-data' or not 1 <= len(options.get(b'boundary',b'')) <= 200:
            fail(400, 'INVALID_MULTIPART', 'Multipart binary input required')
        limit = config.max_file_bytes + 65536
        try:
            declared = int(request.headers['content-length']) if 'content-length' in request.headers else None
        except ValueError:
            fail(400, 'INVALID_MULTIPART', 'Invalid request length')
        if declared is not None and not 0 <= declared <= limit:
            fail(413, 'FILE_TOO_LARGE', 'Input exceeds configured limit')
        if receiving.locked():
            fail(429, 'CONVERTER_CAPACITY', 'Upload capacity reached')
        async with receiving:
            parser = None
            form = None
            total = 0
            async def stream():
                nonlocal total
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > limit:
                        parser.too_large = True
                        raise MultiPartException('Request too large')
                    for offset in range(0,len(chunk),65536):
                        yield chunk[offset:offset+65536]
            parser = BoundedParser(request.headers, stream(), max_files=1, max_fields=6,
                                   max_part_size=4096, max_bytes=config.max_file_bytes)
            try:
                try:
                    async with asyncio.timeout(config.receive_seconds):
                        form = await parser.parse()
                    if not parser.ended:
                        fail(400, 'INVALID_MULTIPART', 'Incomplete multipart input')
                except (MultiPartException, MultipartParseError):
                    fail(413 if parser.too_large else 400,
                         'FILE_TOO_LARGE' if parser.too_large else 'INVALID_MULTIPART', 'Input rejected')
                except TimeoutError:
                    fail(408, 'RECEIVE_TIMEOUT', 'Upload deadline exceeded')
                except ClientDisconnect:
                    fail(400, 'UPLOAD_INTERRUPTED', 'Upload interrupted')
                pairs = form.multi_items()
                if len(pairs) != len(set(form)) or set(form)-({'file'} | set(Options.model_fields)):
                    fail(422, 'INVALID_REQUEST', 'Unknown or repeated form fields')
                file = form.get('file')
                if not isinstance(file, UploadFile) or any(isinstance(value,UploadFile) for key,value in pairs if key != 'file'):
                    fail(422, 'INVALID_REQUEST', 'Exactly one binary file required')
                data = {key:value for key,value in pairs if key != 'file'}
                for key in ('ocr_enabled','generate_preview'):
                    if key in data:
                        if data[key] not in ('true','false'):
                            fail(422, 'INVALID_REQUEST', 'Boolean fields require true or false')
                        data[key] = data[key] == 'true'
                try:
                    info = Options.model_validate(data)
                except ValidationError:
                    fail(422, 'INVALID_REQUEST', 'Invalid conversion metadata')
                languages = info.ocr_languages.split(',') if info.ocr_languages else []
                if any(language not in ('chi_sim','eng') for language in languages) or len(languages) != len(set(languages)):
                    fail(422, 'INVALID_OCR_LANGUAGE', 'OCR language is not allowed')
                if info.ocr_enabled:
                    if not languages_available:fail(422, 'OCR_UNAVAILABLE', 'OCR is not available')
                    if not set(languages or ['eng'])<=set(languages_available):
                        fail(422, 'OCR_LANGUAGE_UNAVAILABLE', 'Requested OCR model is not available')
                elif languages:
                    fail(422, 'OCR_DISABLED', 'Languages require OCR')
                try:
                    return await run_in_threadpool(store.submit, file.file, info)
                except OSError:
                    fail(503, 'CONVERTER_STORAGE_UNAVAILABLE', 'Temporary storage unavailable')
            finally:
                for file in parser._files_to_close_on_error:
                    file.close()
                if form is not None:
                    await form.close()

    @routes.get('/jobs/{id}')
    def job(id: str):
        return store.get(id)

    @routes.get('/jobs/{id}/result')
    def result(id: str):
        return store.get(id, result=True)

    @routes.delete('/jobs/{id}', status_code=204)
    def delete(id: str):
        store.delete(id)
        return Response(status_code=204)

    @routes.get('/artifacts/{ref}')
    def artifact(ref: str):
        file, asset = store.artifact(ref)
        def chunks():
            try:
                while chunk := file.read(65536):
                    yield chunk
            finally:
                file.close()
        return StreamingResponse(chunks(), media_type=asset['media_type'], headers={
            'Content-Length': str(asset['size_bytes']), 'X-Content-Type-Options': 'nosniff',
            'Content-Disposition': 'attachment; filename="artifact"', 'Cache-Control': 'no-store',
            'ETag': '"' + asset['sha256'] + '"'})
    return routes
