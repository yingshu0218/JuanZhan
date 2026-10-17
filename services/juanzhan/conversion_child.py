"""One resource-limited parser subprocess. Paths originate only from ConverterStore."""
import hashlib
import json
from pathlib import Path
import resource
import sys
import uuid


def parse(directory, options, limits):
    from .uploads import sniff
    from .conversion_formats import (DOCX, EPUB, SUPPORTED, FormatError, Output, text_format,
                                     markdown_format, docx_format, epub_format, pdf_format, markdown_artifact)
    from .conversion_html import html_format
    with (directory / 'input').open('rb') as file:
        mime = sniff(file, 'input.txt')
    data = (directory / 'input').read_bytes()
    declared = options['declared_mime']
    # Text subtypes cannot be identified reliably from bytes alone. Accept a validated
    # MIME hint only for textual bytes/BOM; binary signatures always take precedence.
    if mime == 'text/plain' and declared in ('text/markdown','text/html'):
        mime = declared
    elif data.startswith((b'\xff\xfe', b'\xfe\xff', b'\x00\x00\xfe\xff')):
        mime = declared if declared in ('text/plain','text/markdown','text/html') else 'text/plain'
    elif not data and declared in ('text/plain','text/markdown','text/html'):
        mime = declared
    out = Output(limits)
    if options['generate_preview']:out.warn('PREVIEW_NOT_AVAILABLE')
    if declared and declared != mime:out.warn('DECLARED_MIME_MISMATCH')
    result = {'schema_version':'1.0','file_revision_id':options['file_revision_id'],
              'parse_run_id':options['parse_run_id'],'source_mime':mime,
              'parser':{'name':'juanzhan-formats','version':'2.0.0'},'status':'unsupported',
              'language':None,'page_count':None,
              'extraction':{'text_available':False,'ocr_used':False,'ocr_languages':[]},
              'blocks':[],'metadata_candidates':[],'artifacts':[],'warnings':out.warnings}
    if mime not in SUPPORTED:
        out.warn('UNSUPPORTED_INPUT_TYPE')
        return {'result':result}
    adapters={'text/plain':text_format,'text/markdown':markdown_format,'text/html':html_format,
              DOCX:docx_format,EPUB:epub_format,'application/pdf':pdf_format}
    try:
        adapters[mime](data,out)
        text = ''.join(block['text'] for block in out.blocks) if mime=='text/plain' else '\n\n'.join(block['text'] for block in out.blocks)
        assets=[('plain_text','text/plain; charset=utf-8',text),
                ('markdown','text/markdown; charset=utf-8',markdown_artifact(out.blocks))]
        total=0
        for kind,media_type,value in assets:
            content=value.encode('utf-8')
            total+=len(content)
            if total>limits['max_output_bytes']:raise FormatError('RESULT_LIMIT')
            ref=uuid.uuid4().hex
            (directory/ref).write_bytes(content)
            result['artifacts'].append({'kind':kind,'media_type':media_type,'artifact_ref':ref,
                                        'sha256':hashlib.sha256(content).hexdigest(),'size_bytes':len(content)})
        from importlib.metadata import version
        parser_version=version(out.parser) if out.parser in ('pypdf','markdown-it-py') else '2.0.0'
        result.update(status='completed',parser={'name':out.parser,'version':parser_version},
                      page_count=out.page_count,blocks=out.blocks,metadata_candidates=out.candidates,
                      extraction={'text_available':any(block['text'].strip() for block in out.blocks),
                                  'ocr_used':False,'ocr_languages':[]})
        return {'result':result}
    except FormatError as error:
        return {'error':{'code':error.code,'message':'Document could not be converted safely'}}
    except (MemoryError,RecursionError):
        return {'error':{'code':'CONVERSION_RESOURCE_LIMIT','message':'Parser resource limit exceeded'}}
    except Exception:
        return {'error':{'code':'INVALID_DOCUMENT','message':'Malformed or unsupported document structure'}}


def main():
    directory = Path(sys.argv[1])
    options = json.loads((directory / 'options.json').read_bytes())
    limits = json.loads((directory / 'limits.json').read_bytes())
    resource.setrlimit(resource.RLIMIT_AS, (limits['memory_bytes'], limits['memory_bytes']))
    resource.setrlimit(resource.RLIMIT_CPU, (limits['cpu_seconds'], limits['cpu_seconds']))
    resource.setrlimit(resource.RLIMIT_FSIZE, (limits['max_output_bytes'], limits['max_output_bytes']))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    result = parse(directory, options, limits)
    encoded = json.dumps(result, ensure_ascii=False, allow_nan=False).encode()
    if len(encoded) > limits['max_output_bytes']:
        encoded = b'{"error":{"code":"RESULT_LIMIT","message":"Result limit exceeded"}}'
    (directory / 'output.json').write_bytes(encoded)


if __name__ == '__main__':
    main()
