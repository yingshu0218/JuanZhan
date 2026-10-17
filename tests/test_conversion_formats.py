"""Real files through the isolated child and authenticated HTTP protocol."""
from dataclasses import asdict, replace
from io import BytesIO
import hashlib
from pathlib import Path
import uuid
import zipfile
import pytest
from fastapi.testclient import TestClient

from juanzhan.apps import create_app
from juanzhan.config import Settings
from juanzhan.conversion_models import ParseResult
from juanzhan.conversion_store import ConverterConfig
from juanzhan.conversion_formats import FormatError, Output, SUPPORTED, safe_href, markdown_artifact
from format_samples import samples, zipped, pdf
from test_converter import completed, HEADERS


def convert(client, mime, content):
    response=client.post('/v1/jobs',headers=HEADERS,data={'file_revision_id':'real-revision','parse_run_id':uuid.uuid4().hex,'declared_mime':mime,'generate_preview':'false'},files={'file':('untrusted-name',content)})
    assert response.status_code==202,response.text
    id=response.json()['job_id']
    job=completed(client,id)
    result=client.get('/v1/jobs/'+id+'/result',headers=HEADERS).json() if job['status']=='completed' else None
    return id,job,result


@pytest.fixture
def client(tmp_path):
    config=ConverterConfig(root=tmp_path/'spool')
    with TestClient(create_app('converter',Settings(tmp_path/'archive','private-converter-token'),converter_config=config)) as client:
        yield client


@pytest.mark.parametrize('format',['txt','md','html','docx','epub','pdf'])
def test_six_real_formats_uniform_result_and_verified_artifacts(client,format):
    mime,content=samples()[format]
    before=hashlib.sha256(content).hexdigest()
    id,job,result=convert(client,mime,content)
    assert job['status']=='completed',job
    ParseResult.model_validate(result)
    assert result['status']=='completed' and result['source_mime']==mime
    assert result['extraction']['text_available'] and not result['extraction']['ocr_used']
    assert [block['index'] for block in result['blocks']]==list(range(len(result['blocks'])))
    assert all(block['confidence'] is None for block in result['blocks'])
    assert {asset['kind'] for asset in result['artifacts']}=={'plain_text','markdown'}
    for asset in result['artifacts']:
        response=client.get('/v1/artifacts/'+asset['artifact_ref'],headers=HEADERS)
        assert len(response.content)==asset['size_bytes']
        assert hashlib.sha256(response.content).hexdigest()==asset['sha256']
        assert response.headers['x-content-type-options']=='nosniff'
    assert hashlib.sha256(content).hexdigest()==before
    blocks=result['blocks']
    if format=='pdf':
        assert result['page_count']==2
        assert {b['locator']['page'] for b in blocks}=={1,2}
        assert 'Real PDF page 1' in blocks[0]['text']
        assert 'PDF_READING_ORDER_AND_TABLES_UNVERIFIED' in result['warnings']
    else:
        assert result['page_count'] is None
        assert all('page' not in b['locator'] for b in blocks)
    if format in ('md','html','docx'):
        assert {'heading','list_item','table'} <= {b['type'] for b in blocks}
        table=next(b for b in blocks if b['type']=='table')['table']
        assert table['headers'] and table['rows']
    if format=='epub':
        assert blocks[0]['text']=='第一章'
        assert [b['locator']['spine_index'] for b in blocks]==[0,0,1,1]
        assert {b['locator']['href'] for b in blocks}=={'OEBPS/first.xhtml','OEBPS/second.xhtml'}
        assert any(c['source']=='epub_manifest' and c['key']=='author' for c in result['metadata_candidates'])
    if format=='html':
        assert not any('NEVER_EXECUTE' in b['text'] or 'HIDDEN_SECRET' in b['text'] for b in blocks)
        assert any(c['source']=='html_meta' and c['value']=='网页作者' for c in result['metadata_candidates'])
    assert client.delete('/v1/jobs/'+id,headers=HEADERS).status_code==204


@pytest.mark.parametrize('encoding',['utf-8-sig','utf-16','utf-32'])
def test_bom_text_decoding_has_real_character_ranges(client,encoding):
    text='真实字符 🗃\n\n下一段\n'
    _,job,result=convert(client,'text/plain',text.encode(encoding))
    assert job['status']=='completed',job
    assert ''.join(b['text'] for b in result['blocks'])==text
    for block in result['blocks']:
        loc=block['locator']
        assert text[loc['start']:loc['end']]==block['text']


def test_pdf_no_text_is_honest_and_encryption_fails(client):
    id,job,result=convert(client,'application/pdf',pdf(blank=True))
    assert job['status']=='completed'
    assert not result['extraction']['text_available'] and result['page_count']==2
    assert 'NO_TEXT_LAYER_OCR_REQUIRED' in result['warnings']
    client.delete('/v1/jobs/'+id,headers=HEADERS)
    _,job,result=convert(client,'application/pdf',pdf(encrypted=True))
    assert job['status']=='failed' and job['error']['error']['code']=='PDF_PASSWORD_REQUIRED'
    assert result is None


@pytest.mark.parametrize('entries,code',[
    ({'../outside':'bad'},'UNSAFE_ARCHIVE'),
    ({'safe\\outside':'bad'},'UNSAFE_ARCHIVE'),
    ({'huge':'a'*100000},'ARCHIVE_LIMIT'),
    ({'word/document.xml':'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>','[Content_Types].xml':'<x/>'},'UNSAFE_OR_INVALID_XML'),
])
def test_unsafe_docx_archive_and_xml_are_rejected(client,entries,code):
    package={'[Content_Types].xml':'<Types/>','word/document.xml':'<document><body/></document>',**entries}
    _,job,result=convert(client,'application/vnd.openxmlformats-officedocument.wordprocessingml.document',zipped(package))
    assert job['status']=='failed' and job['error']['error']['code']==code


@pytest.mark.parametrize('href',['../../outside','https://example.invalid/file','//example.invalid/file','%2e%2e/%2e%2e/out','/absolute','..\\evil'])
def test_package_references_cannot_escape_or_fetch(href):
    with pytest.raises(FormatError):safe_href('OEBPS/content.opf',href)


def test_markdown_asset_contains_no_active_markup_or_links(client):
    content=b'# Title\n\n<script>SECRET</script>\n\nText <script>SECRET</script> <img src=x onerror=bad()> [label](javascript:alert(1))\n'
    _,job,result=convert(client,'text/markdown',content)
    assert job['status']=='completed'
    for asset in result['artifacts']:
        text=client.get('/v1/artifacts/'+asset['artifact_ref'],headers=HEADERS).text
        assert '<script>' not in text and '<img' not in text and 'SECRET' not in text
        if asset['kind']=='markdown':
            assert '[label](' not in text  # Literal unsafe link syntax must not become an active link.


def test_page_and_zip_member_limits(tmp_path):
    config=ConverterConfig(root=tmp_path/'spool',max_pages=1,max_archive_member_bytes=1024)
    with TestClient(create_app('converter',Settings(tmp_path/'archive','private-converter-token'),converter_config=config)) as client:
        _,job,_=convert(client,'application/pdf',pdf())
        assert job['error']['error']['code']=='PAGE_LIMIT'
        content=zipped({'[Content_Types].xml':'<x/>','word/document.xml':'<x>'+('not compressible '+str(uuid.uuid4()))*50+'</x>'},compression=zipfile.ZIP_STORED)
        _,job,_=convert(client,'application/vnd.openxmlformats-officedocument.wordprocessingml.document',content)
        assert job['error']['error']['code']=='ARCHIVE_LIMIT'


def test_html_does_not_load_remote_resources(client):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    hits=[]
    class Probe(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(200);self.end_headers()
        def log_message(self,*_):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Probe)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        url=f'http://127.0.0.1:{server.server_port}/must-not-fetch'
        data=f'<html><body><p>Visible</p><script src="{url}">HIDDEN</script><style>@import url({url});</style><iframe src="{url}"></iframe><img src="{url}" alt="alt"/></body></html>'.encode()
        _,job,result=convert(client,'text/html',data)
        assert job['status']=='completed' and hits==[]
        assert all('HIDDEN' not in b['text'] for b in result['blocks'])
        assert 'ACTIVE_MARKUP_AND_RESOURCES_OMITTED' in result['warnings']
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)


def test_epub_namespace_and_remote_spine_rejection(client):
    from format_samples import epub
    with zipfile.ZipFile(BytesIO(epub())) as archive:entries={name:archive.read(name) for name in archive.namelist()}
    entries['OEBPS/first.xhtml']=b'<x:html xmlns:x="http://www.w3.org/1999/xhtml"><x:head><x:title>omit</x:title></x:head><x:body><x:h1>Prefixed heading</x:h1><x:p>content</x:p></x:body></x:html>'
    id,job,result=convert(client,'application/epub+zip',zipped(entries))
    assert job['status']=='completed' and result['blocks'][0]['type']=='heading'
    assert result['blocks'][0]['text']=='Prefixed heading'
    client.delete('/v1/jobs/'+id,headers=HEADERS)
    entries['OEBPS/content.opf']=entries['OEBPS/content.opf'].replace(b'href="first.xhtml"',b'href="https://example.invalid/remote.xhtml"')
    _,job,result=convert(client,'application/epub+zip',zipped(entries))
    assert job['status']=='failed' and job['error']['error']['code']=='UNSAFE_PACKAGE_REFERENCE'


def test_zip_symlinks_and_duplicate_members_rejected(client):
    for symlink in (True,False):
        output=BytesIO()
        with zipfile.ZipFile(output,'w') as archive:
            archive.writestr('[Content_Types].xml','<x/>')
            archive.writestr('word/document.xml','<document><body/></document>')
            if symlink:
                entry=zipfile.ZipInfo('link')
                entry.create_system=3;entry.external_attr=0o120777<<16
                archive.writestr(entry,'/etc/passwd')
            else:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore',UserWarning)
                    archive.writestr('word/document.xml','<x/>')
        id,job,_=convert(client,'application/vnd.openxmlformats-officedocument.wordprocessingml.document',output.getvalue())
        assert job['status']=='failed' and job['error']['error']['code']=='UNSAFE_ARCHIVE'
        client.delete('/v1/jobs/'+id,headers=HEADERS)


def test_pdf_chinese_unicode_mapping(client):
    from format_samples import chinese_pdf
    _,job,result=convert(client,'application/pdf',chinese_pdf())
    assert job['status']=='completed',job
    assert '中文资料' in ''.join(block['text'] for block in result['blocks'])
    assert result['page_count']==1 and result['blocks'][0]['locator']=={'kind':'page','page':1}


def test_pdf_decoded_stream_limit_applies_to_contentstream_objects(tmp_path):
    from pypdf import PdfReader,PdfWriter
    from pypdf.generic import DecodedStreamObject,NameObject
    reader=PdfReader(BytesIO(pdf(pages=1)))
    writer=PdfWriter();writer.add_page(reader.pages[0])
    stream=DecodedStreamObject();stream.set_data(reader.pages[0].get_contents().get_data()+b' '*2048)
    writer.pages[0][NameObject('/Contents')]=writer._add_object(stream.flate_encode())
    data=BytesIO();writer.write(data)
    config=ConverterConfig(root=tmp_path/'spool',max_archive_member_bytes=1024)
    with TestClient(create_app('converter',Settings(tmp_path/'archive','private-converter-token'),converter_config=config)) as client:
        _,job,_=convert(client,'application/pdf',data.getvalue())
        assert job['status']=='failed' and job['error']['error']['code']=='PDF_STREAM_LIMIT'


def test_docx_false_header_and_disabled_numbering_do_not_invent_semantics(client):
    from format_samples import docx
    with zipfile.ZipFile(BytesIO(docx())) as archive:entries={name:archive.read(name) for name in archive.namelist()}
    entries['word/document.xml']=entries['word/document.xml'].replace(b'<w:tblHeader/>',b'<w:tblHeader w:val="false"/>')
    entries['word/styles.xml']=entries['word/styles.xml'].replace(b'<w:numId w:val="1"/>',b'<w:numId w:val="0"/>')
    _,job,result=convert(client,'application/vnd.openxmlformats-officedocument.wordprocessingml.document',zipped(entries))
    assert job['status']=='completed'
    table=next(block for block in result['blocks'] if block['type']=='table')['table']
    assert table['headers']==[] and table['rows']==[['字段'],['内容']]
    assert next(block for block in result['blocks'] if block['text']=='清单项目')['type']=='paragraph'
