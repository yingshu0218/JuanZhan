"""All declared MIME families, OCR, encodings and explicit unsupported/corrupt boundaries."""
import hashlib
import json
import os
from pathlib import Path
import uuid
import pytest
from test_parsing import pipeline,upload
from juanzhan.worker import Worker
from juanzhan.database import connect
from format_samples import samples,raster_sample,pdf,zipped


def process(pipeline,data,name,expected='completed'):
    settings,client,_,_=pipeline
    saved=upload(pipeline,data,name);Worker(settings).run_once()
    detail=client.get('/api/v1/documents/'+saved['document_id']).json()
    assert detail['processing_status']==expected,(name,detail)
    result=client.get('/api/v1/documents/'+saved['document_id']+'/overview')
    assert result.status_code==200,(name,result.text)
    # Parsing does not remove or mutate the original, even when unsupported/failed.
    response=client.get('/api/v1/documents/'+saved['document_id']+'/download')
    assert response.status_code==200,response.text
    assert hashlib.sha256(response.content).digest()==hashlib.sha256(data).digest()
    return saved,detail,result.json()


@pytest.mark.parametrize('extension',list(samples())+['markdown','htm'])
def test_all_six_document_formats_and_aliases(pipeline,extension):
    key={'markdown':'md','htm':'html'}.get(extension,extension)
    _,data=samples()[key]
    _,_,summary=process(pipeline,data,'sample.'+extension)
    assert summary['points'] and summary['text_available']
    assert summary['parse_run_id'] and summary['content_revision_id']
    for point in summary['points']:
        assert point['sources'] and point['sources'][0]['block_id']


@pytest.mark.parametrize('encoding',['utf-8','utf-8-sig','utf-16','utf-32'])
def test_text_encodings_are_identified_and_summarized(pipeline,encoding):
    _,_,summary=process(pipeline,'本次会议确认项目验收。\n\n负责人：王明。'.encode(encoding),'meeting.txt')
    assert '项目验收' in str(summary['points']) and '王明' in str(summary['points'])


@pytest.mark.parametrize('format,extension',[('PNG','png'),('JPEG','jpg'),('JPEG','jpeg'),('TIFF','tif'),('TIFF','tiff'),('PDF','pdf')])
def test_every_raster_family_ocr_off_then_explicit_real_ocr(pipeline,format,extension):
    settings,client,headers,_=pipeline;data=raster_sample(format)
    saved,detail,summary=process(pipeline,data,'scan.'+extension)
    assert not summary['text_available'] and not summary['points'] and not summary['ocr_used']
    root='/api/v1/documents/'+saved['document_id']
    response=client.post(root+'/reprocess',headers=headers,json={'request_id':uuid.uuid4().hex,'expected_document_version':detail['document_version'],
        'expected_revision_id':detail['current_revision_id'],'force':True,'ocr':True,'ocr_languages':'eng','generate_preview':False})
    assert response.status_code==202,response.text
    Worker(settings).run_once()
    result=client.get(root+'/overview').json()
    assert result['ocr_used'] and result['text_available'],result
    assert 'scanned archive 2026' in str(result['points']),result
    assert 'OCR_TEXT_REQUIRES_REVIEW' in result['warnings']
    assert client.get(root+'/download').content==data


@pytest.mark.parametrize('name,data,status',[
    ('encrypted.pdf',pdf(encrypted=True),'failed'),
    ('broken.pdf',b'%PDF-1.7\nnot a PDF','failed'),
    ('broken.docx',zipped({'[Content_Types].xml':'<Types/>','word/document.xml':'<broken'}),'failed'),
    ('archive.zip',zipped({'note.txt':'Preserved original'}),'unsupported'),
    ('document.rtf',b'{\\rtf1\\ansi This is a real RTF paragraph.\\par}','unsupported'),
    ('empty.txt',b'','unsupported'),
    ('invalid-utf16.bin',b'\xff\xfe\x13\x00\x00\x01','failed'),
    ('raw.bin',b'\x00binary','unsupported'),
])
def test_corrupt_protected_and_unsupported_originals_remain_available(pipeline,name,data,status):
    _,_,summary=process(pipeline,data,name,status)
    assert not summary['points'] and not summary['parse_run_id']


def test_csv_is_plain_text_fallback_not_a_structured_spreadsheet_parser(pipeline):
    _,_,summary=process(pipeline,'设备,状态\n主机,已验收\n'.encode(),'inventory.csv')
    assert summary['points'] and '主机,已验收' in str(summary['points'])


@pytest.mark.parametrize('name',['sample.doc','sample.xls','sample.xlsx','sample.ppt','sample.pptx'])
def test_real_office_formats_outside_declared_support_are_not_false_success(pipeline,name):
    directory=os.environ.get('JUANZHAN_FORMAT_FIXTURES')
    if not directory:pytest.skip('Set JUANZHAN_FORMAT_FIXTURES to pinned Apache POI acceptance samples')
    data=(Path(directory)/name).read_bytes()
    manifest=json.loads((Path(directory)/'manifest.json').read_text())
    expected=next(item for item in manifest if item['name']==name)
    assert hashlib.sha256(data).hexdigest()==expected['sha256']
    if name.endswith(('.xlsx','.pptx')):
        from io import BytesIO
        from zipfile import ZipFile
        with ZipFile(BytesIO(data)) as package:assert ('xl/workbook.xml' if name.endswith('.xlsx') else 'ppt/presentation.xml') in package.namelist()
    else:assert data.startswith(bytes.fromhex('d0cf11e0a1b11ae1'))
    process(pipeline,data,name,'unsupported')


@pytest.mark.parametrize('format,extension',[('GIF','gif'),('BMP','bmp'),('WEBP','webp')])
def test_other_real_image_formats_are_explicitly_unsupported(pipeline,format,extension):
    process(pipeline,raster_sample(format),'image.'+extension,'unsupported')


@pytest.mark.parametrize('extension,mime',[('odt','application/vnd.oasis.opendocument.text'),('ods','application/vnd.oasis.opendocument.spreadsheet'),('odp','application/vnd.oasis.opendocument.presentation')])
def test_other_zip_document_families_do_not_claim_text_parsing(pipeline,extension,mime):
    data=zipped({'mimetype':mime,'content.xml':'<?xml version="1.0"?><office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"><office:body/></office:document-content>'})
    process(pipeline,data,'document.'+extension,'unsupported')
