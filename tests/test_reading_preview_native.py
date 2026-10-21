"""Opt-in real private renderer integration, never a mocked conversion response."""
import os
import json
import zipfile
from io import BytesIO
import pytest
from test_parsing import pipeline,upload
from format_samples import docx,zipped
from juanzhan.worker import Worker

pytestmark=pytest.mark.skipif(not os.getenv('OFFICE_PREVIEW_URL'),reason='Requires isolated native Office service')


def test_native_preview_persists_pdf_without_changing_original_or_document(pipeline):
    settings,client,headers,space=pipeline
    # Parser fixtures omit package content types; native Office needs a valid OPC package.
    with zipfile.ZipFile(BytesIO(docx())) as package:
        parts={name:package.read(name) for name in package.namelist()}
    parts['[Content_Types].xml']='<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>'
    original=zipped(parts);saved=upload(pipeline,original,'source.docx');document=saved['document_id']
    path='/api/v1/documents/'+document
    before=client.get(path).json()
    payload={'expected_document_version':before['document_version'],'revision_id':before['current_revision_id'],'request_id':'native-preview'}
    receipt=client.post(path+'/reading-preview',headers=headers,json=payload)
    assert receipt.status_code==202,receipt.text
    assert client.post(path+'/reading-preview',headers=headers,json=payload).json()==receipt.json()
    for _ in range(8):
        Worker(settings).run_once()
        result=client.get('/api/v1/jobs/'+receipt.json()['job_id']).json()
        if result['status'] in ('completed','failed'):break
    assert result['status']=='completed',json.dumps(result)
    status=client.get(path+'/reading-preview').json()
    assert status['state']=='ready' and status['renderer']
    pdf=client.get(path+'/reading-preview/file',params={'revision_id':before['current_revision_id']})
    assert pdf.status_code==200 and pdf.content.startswith(b'%PDF-')
    assert pdf.headers['x-revision-id']==before['current_revision_id']
    assert pdf.headers['x-content-type-options']=='nosniff'
    assert client.get(path+'/download').content==original
    after=client.get(path).json()
    assert after['document_version']==before['document_version']
    assert after['current_revision_id']==before['current_revision_id']
    assert client.get('/api/v1/system/storage').json()['reading_preview_count']==1
    from juanzhan.backup import create,restore
    from juanzhan.config import Settings
    from juanzhan.database import connect
    from juanzhan.storage import ManagedStore
    bundle=settings.data_dir.parent/'reading-backup';target=settings.data_dir.parent/'reading-restored'
    create(settings,bundle);restore(bundle,target)
    recovered=Settings(target,'')
    with connect(recovered.database) as db:
        cache=db.execute('SELECT storage_key FROM reading_previews WHERE revision_id=?',(before['current_revision_id'],)).fetchone()
        assert cache is not None
    with ManagedStore(recovered.data_dir/'derived').open(cache[0]) as source:assert source.read()==pdf.content


def test_native_multipage_tiff_is_readable_without_replacing_source(pipeline):
    from PIL import Image
    from pypdf import PdfReader
    settings,client,headers,space=pipeline
    image=Image.new('RGB',(120,160),'white');second=Image.new('RGB',(120,160),'green')
    stream=BytesIO();image.save(stream,format='TIFF',save_all=True,append_images=[second]);original=stream.getvalue()
    saved=upload(pipeline,original,'two-pages.tiff');path='/api/v1/documents/'+saved['document_id']
    before=client.get(path).json()
    receipt=client.post(path+'/reading-preview',headers=headers,json={'expected_document_version':before['document_version'],'revision_id':before['current_revision_id'],'request_id':'tiff-preview'})
    assert receipt.status_code==202,receipt.text
    for _ in range(8):
        Worker(settings).run_once()
        result=client.get('/api/v1/jobs/'+receipt.json()['job_id']).json()
        if result['status'] in ('completed','failed'):break
    assert result['status']=='completed',json.dumps(result)
    response=client.get(path+'/reading-preview/file',params={'revision_id':before['current_revision_id']})
    assert response.status_code==200
    assert len(PdfReader(BytesIO(response.content)).pages)==2
    assert client.get(path+'/download').content==original
