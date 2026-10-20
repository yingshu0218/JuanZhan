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
    from .conversion_office import OFFICE_TYPES, XLSX, PPTX, xlsx_format, pptx_format, odf_format, delimited_format
    from .conversion_raster import Raster, IMAGES
    from contextlib import nullcontext
    with (directory / 'input').open('rb') as file:
        mime = sniff(file, 'input.txt')
    data = (directory / 'input').read_bytes()
    declared = options['declared_mime']
    # Text subtypes cannot be identified reliably from bytes alone. Accept a validated
    # MIME hint only for textual bytes/BOM; binary signatures always take precedence.
    text_types=('text/plain','text/markdown','text/html','text/csv','text/tab-separated-values')
    if mime == 'text/plain' and declared in text_types:
        mime = declared
    elif data.startswith((b'\xff\xfe', b'\xfe\xff', b'\x00\x00\xfe\xff')):
        mime = declared if declared in text_types else 'text/plain'
    elif not data and declared in text_types:
        mime = declared
    out = Output(limits)
    raster_mime=mime in IMAGES or mime=='application/pdf'
    if options['generate_preview'] and not raster_mime:out.warn('PREVIEW_NOT_AVAILABLE')
    if declared and declared != mime:out.warn('DECLARED_MIME_MISMATCH')
    result = {'schema_version':'1.0','file_revision_id':options['file_revision_id'],
              'parse_run_id':options['parse_run_id'],'source_mime':mime,
              'parser':{'name':'juanzhan-formats','version':'2.0.0'},'status':'unsupported',
              'language':None,'page_count':None,
              'extraction':{'text_available':False,'ocr_used':False,'ocr_languages':[]},
              'blocks':[],'metadata_candidates':[],'artifacts':[],'warnings':out.warnings}
    if mime not in SUPPORTED and mime not in IMAGES:
        out.warn('UNSUPPORTED_INPUT_TYPE')
        return {'result':result}
    adapters={'text/plain':text_format,'text/markdown':markdown_format,'text/html':html_format,
              DOCX:docx_format,EPUB:epub_format,'application/pdf':pdf_format}
    adapters.update({mime:odf_format for mime in OFFICE_TYPES})
    adapters.update({XLSX:xlsx_format,PPTX:pptx_format})
    adapters.update({'text/csv':delimited_format,'text/tab-separated-values':lambda data,out:delimited_format(data,out,'\t')})
    try:
        needs_raster=raster_mime and (options['ocr_enabled'] or options['generate_preview'] or mime in IMAGES)
        with Raster(data,mime,out,options) if needs_raster else nullcontext() as raster:
            if mime in IMAGES:
                out.parser='juanzhan-raster'
                out.page_count=raster.count
                for index in range(raster.count):
                    if index:out.add('page_break','',{'kind':'page','page':index+1})
                    if options['ocr_enabled']:raster.recognize(index)
                    else:out.warn('IMAGE_OCR_DISABLED')
            elif mime=='application/pdf':
                pdf_format(data,out,raster.recognize if options['ocr_enabled'] else None)
            else:
                adapters[mime](data,out)
                if options['ocr_enabled']:out.warn('OCR_NOT_APPLICABLE')
            preview_assets=raster.previews() if raster and options['generate_preview'] else []
            ocr_used=bool(raster and raster.used)
            ocr_languages=raster.languages if ocr_used else []
        text = ''.join(block['text'] for block in out.blocks) if mime=='text/plain' else '\n\n'.join(block['text'] for block in out.blocks)
        assets=[('plain_text','text/plain; charset=utf-8',text),
                ('markdown','text/markdown; charset=utf-8',markdown_artifact(out.blocks))]+preview_assets
        total=0
        for kind,media_type,value in assets:
            content=value.encode('utf-8') if isinstance(value,str) else value
            total+=len(content)
            if total>limits['max_output_bytes']:raise FormatError('RESULT_LIMIT')
            ref=uuid.uuid4().hex
            (directory/ref).write_bytes(content)
            result['artifacts'].append({'kind':kind,'media_type':media_type,'artifact_ref':ref,
                                        'sha256':hashlib.sha256(content).hexdigest(),'size_bytes':len(content)})
        from importlib.metadata import version
        parser_version=version(out.parser) if out.parser in ('pypdf','markdown-it-py') else '2.0.0'
        if needs_raster:
            parser_version+=';pypdfium2='+version('pypdfium2')+';Pillow='+version('Pillow')
            if ocr_used:parser_version+=';tesserocr='+version('tesserocr')
        result.update(status='completed',parser={'name':out.parser,'version':parser_version},
                      page_count=out.page_count,blocks=out.blocks,metadata_candidates=out.candidates,
                      extraction={'text_available':any(block['text'].strip() for block in out.blocks),
                                  'ocr_used':ocr_used,'ocr_languages':ocr_languages})
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
