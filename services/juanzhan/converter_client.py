"""Internal Archive transport. Never writes business metadata or promotes unverified bytes."""
from contextlib import contextmanager
import hashlib
import json
import os
import re
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import uuid

from pydantic import ValidationError
from .conversion_models import Artifact, Options, ParseResult


class ConverterClientError(Exception):
    def __init__(self, code, status=None):
        self.code, self.status = code, status
        super().__init__(code)  # No raw upstream paths, response body, credentials or URLs.


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ConverterClient:
    def __init__(self, base_url, token, *, timeout=10, max_json_bytes=16*1024*1024,
                 max_artifact_bytes=16*1024*1024, max_file_bytes=4*1024*1024):
        parsed = urlsplit(base_url)
        if (parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or
                parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment or
                not token or any(char in token for char in '\r\n') or not 0 < timeout <= 300 or
                not all(0 < value <= 64*1024*1024 for value in (max_json_bytes,max_artifact_bytes,max_file_bytes))):
            raise ValueError('Invalid internal converter configuration')
        self.base = base_url.rstrip('/')
        self.token = token
        self.timeout = timeout
        self.max_json_bytes = max_json_bytes
        self.max_artifact_bytes = max_artifact_bytes
        self.max_file_bytes = max_file_bytes
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    @classmethod
    def from_env(cls):
        return cls(os.getenv('CONVERTER_URL','http://converter:8000'), os.getenv('CONVERTER_SERVICE_TOKEN',''))

    @staticmethod
    def identity(id):
        if not isinstance(id,str) or not re.fullmatch('[0-9a-f]{32}', id):
            raise ConverterClientError('INVALID_CONVERTER_ID')
        return id

    def open(self, path, *, method='GET', data=None, headers=None, timeout=None):
        request = Request(self.base + path, method=method, data=data, headers={
            'Authorization': 'Bearer ' + self.token, **(headers or {})})
        try:
            return self.opener.open(request, timeout=timeout or self.timeout)
        except HTTPError as exc:
            exc.close()
            raise ConverterClientError('CONVERTER_HTTP_ERROR', exc.code) from None
        except (OSError, URLError, ValueError):
            raise ConverterClientError('CONVERTER_UNAVAILABLE') from None

    def json(self, path, **kwargs):
        try:
            with self.open(path, **kwargs) as response:
                deadline = time.monotonic() + (kwargs.get('timeout') or self.timeout)
                content = bytearray()
                while chunk := response.read1(65536):
                    content.extend(chunk)
                    if len(content) > self.max_json_bytes or time.monotonic() > deadline:
                        raise ConverterClientError('CONVERTER_RESPONSE_LIMIT')
                if response.headers.get_content_type() != 'application/json':
                    raise ConverterClientError('INVALID_CONVERTER_RESPONSE')
                # JSON duplicate keys and NaN must not acquire meaning after validation.
                def pairs(items):
                    result = {}
                    for key,value in items:
                        if key in result:
                            raise ValueError('Repeated JSON key')
                        result[key] = value
                    return result
                return json.loads(content, object_pairs_hook=pairs,
                                  parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except ConverterClientError:
            raise
        except (ValueError, OSError, RecursionError):
            raise ConverterClientError('INVALID_CONVERTER_RESPONSE') from None

    def capabilities(self):
        result = self.json('/v1/capabilities')
        if not isinstance(result,dict) or not isinstance(result.get('schema_versions'),list) or '1.0' not in result['schema_versions']:
            raise ConverterClientError('INCOMPATIBLE_CONVERTER')
        return result

    def submit(self, stream, options):
        options = Options.model_validate(options)
        boundary = 'juanzhan-' + uuid.uuid4().hex
        def multipart():
            # Options are validated IDs/booleans/text, never headers or paths.
            for key,value in options.model_dump().items():
                value = ('true' if value else 'false') if isinstance(value,bool) else value
                yield (f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n').encode()
            yield (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="input"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
            size = 0
            while chunk := stream.read(65536):
                size += len(chunk)
                if size > self.max_file_bytes:
                    raise ConverterClientError('CONVERTER_INPUT_LIMIT')
                yield chunk
            yield f'\r\n--{boundary}--\r\n'.encode()
        result = self.json('/v1/jobs', method='POST', data=multipart(), headers={
            'Content-Type': 'multipart/form-data; boundary=' + boundary})
        return self.validate_job(result, reference=True)

    def validate_job(self, value, *, reference=False):
        if not isinstance(value,dict) or value.get('status') not in ('queued','running','completed','failed','cancelled'):
            raise ConverterClientError('INVALID_CONVERTER_RESPONSE')
        self.identity(value.get('job_id',''))
        if not reference and (type(value.get('attempts')) is not int or value['attempts'] < 0):
            raise ConverterClientError('INVALID_CONVERTER_RESPONSE')
        return value

    def job(self, id, *, timeout=None):
        result = self.validate_job(self.json('/v1/jobs/' + self.identity(id), timeout=timeout))
        if result['job_id'] != id:
            raise ConverterClientError('CONVERTER_IDENTITY_MISMATCH')
        return result

    def wait(self, id, *, deadline_seconds=60, interval=.1):
        if not 0 < deadline_seconds <= 600 or not .01 <= interval <= 5:
            raise ValueError('Invalid polling budget')
        deadline = time.monotonic() + deadline_seconds
        while True:
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise ConverterClientError('CONVERTER_WAIT_TIMEOUT')
            result = self.job(id, timeout=min(remaining,self.timeout))
            if result['status'] not in ('queued','running'):
                return result
            time.sleep(min(interval,max(0,deadline-time.monotonic())))

    def result(self, id, *, file_revision_id, parse_run_id):
        try:
            result = ParseResult.model_validate(self.json('/v1/jobs/' + self.identity(id) + '/result'))
        except ValidationError:
            raise ConverterClientError('INVALID_CONVERTER_RESULT') from None
        if result.file_revision_id != file_revision_id or result.parse_run_id != parse_run_id:
            raise ConverterClientError('CONVERTER_IDENTITY_MISMATCH')
        return result.model_dump(exclude_unset=True)

    @contextmanager
    def artifact(self, asset):
        try:
            asset = Artifact.model_validate(asset)
        except ValidationError:
            raise ConverterClientError('INVALID_CONVERTER_ARTIFACT') from None
        if asset.size_bytes > self.max_artifact_bytes:
            raise ConverterClientError('CONVERTER_ARTIFACT_LIMIT')
        with tempfile.SpooledTemporaryFile(max_size=65536,mode='w+b') as file:
            try:
                with self.open('/v1/artifacts/' + asset.artifact_ref) as response:
                    digest = hashlib.sha256()
                    size = 0
                    deadline = time.monotonic() + self.timeout
                    while chunk := response.read1(65536):
                        size += len(chunk)
                        if size > min(asset.size_bytes,self.max_artifact_bytes) or time.monotonic() > deadline:
                            raise ConverterClientError('CONVERTER_ARTIFACT_LIMIT')
                        digest.update(chunk)
                        file.write(chunk)
                    if size != asset.size_bytes or digest.hexdigest() != asset.sha256:
                        raise ConverterClientError('CONVERTER_ARTIFACT_INTEGRITY')
            except OSError:
                raise ConverterClientError('CONVERTER_UNAVAILABLE') from None
            file.seek(0)
            yield file

    def delete(self, id):
        with self.open('/v1/jobs/' + self.identity(id), method='DELETE') as response:
            if response.status != 204:
                raise ConverterClientError('INVALID_CONVERTER_RESPONSE')
