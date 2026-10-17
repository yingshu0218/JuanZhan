"""Actual raster/OCR engine, subprocess, SQLite and authenticated HTTP integration."""
from dataclasses import replace
from io import BytesIO
from pathlib import Path
import hashlib

from fastapi.testclient import TestClient
import pytest
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter

from juanzhan.apps import create_app
from juanzhan.config import Settings
from juanzhan.conversion_store import ConverterConfig
from test_converter import HEADERS, submit, completed


from format_samples import raster_sample as scan


def run(tmp_path,content,config=None,**options):
    config=config or ConverterConfig(root=tmp_path/'spool')
    app=create_app('converter',Settings(tmp_path/'archive','private-converter-token'),converter_config=config)
    with TestClient(app) as client:
        response=submit(client,content,**options)
        assert response.status_code==202,response.text
        job=completed(client,response.json()['job_id'])
        if job['status']!='completed':return job,None,[]
        result=client.get('/v1/jobs/'+job['job_id']+'/result',headers=HEADERS).json()
        assets=[]
        for artifact in result['artifacts']:
            data=client.get('/v1/artifacts/'+artifact['artifact_ref'],headers=HEADERS)
            assert data.status_code==200,data.text
            assert hashlib.sha256(data.content).hexdigest()==artifact['sha256']
            assets.append((artifact,data.content))
        return job,result,assets

@pytest.mark.parametrize('format',['PNG','JPEG','TIFF','PDF'])
def test_real_english_scan_and_sanitized_preview(tmp_path,format):
    content=scan(format)
    before=hashlib.sha256(content).hexdigest()
    if format=='PDF':assert not PdfReader(BytesIO(content)).pages[0].extract_text().strip()
    job,result,assets=run(tmp_path,content,ocr_enabled='true')
    assert job['status']=='completed',job
    assert result['extraction']=={'text_available':True,'ocr_used':True,'ocr_languages':['eng']}
    assert 'scanned archive 2026' in '\n'.join(b['text'] for b in result['blocks'])
    assert result['blocks'][0]['locator']=={'kind':'page','page':1}
    assert 0<=result['blocks'][0]['confidence']<=1
    assert 'OCR_TEXT_REQUIRES_REVIEW' in result['warnings']
    preview=[data for a,data in assets if a['kind']=='thumbnail']
    assert len(preview)==1
    with Image.open(BytesIO(preview[0])) as image:
        assert image.format=='PNG' and max(image.size)<=1024 and not image.getexif()
    assert hashlib.sha256(content).hexdigest()==before


def test_real_chinese_scan(tmp_path):
    job,result,_=run(tmp_path,scan(text='真实中文档案 测试识别'),ocr_enabled='true',ocr_languages='chi_sim,eng',generate_preview='false')
    assert job['status']=='completed',job
    text=''.join(b['text'] for b in result['blocks']).replace(' ','')
    assert '真实中文档案' in text and '测试识别' in text,text
    assert result['extraction']['ocr_languages']==['chi_sim','eng']


def test_mixed_pdf_only_missing_text_is_ocr(tmp_path):
    from format_samples import pdf
    writer=PdfWriter()
    writer.add_page(PdfReader(BytesIO(pdf(pages=1))).pages[0])
    writer.add_page(PdfReader(BytesIO(scan('PDF'))).pages[0])
    data=BytesIO();writer.write(data)
    job,result,_=run(tmp_path,data.getvalue(),ocr_enabled='true',generate_preview='false')
    assert job['status']=='completed',job
    text=[b for b in result['blocks'] if b['text']]
    assert text[0]['text'].strip()=='Real PDF page 1' and text[0]['confidence'] is None
    assert text[1]['locator']['page']==2 and text[1]['confidence'] is not None
    assert result['page_count']==2


def test_ocr_off_preview_limits_and_model_off(tmp_path):
    config=ConverterConfig(root=tmp_path/'spool',enable_ocr=False,max_preview_pages=1)
    job,result,assets=run(tmp_path,scan('TIFF',pages=2),config=config)
    assert job['status']=='completed',job
    assert not result['extraction']['ocr_used'] and not result['extraction']['text_available']
    assert result['page_count']==2 and 'PREVIEW_TRUNCATED' in result['warnings']
    assert len([a for a,_ in assets if a['kind']=='thumbnail'])==1
    app=create_app('converter',Settings(tmp_path/'archive','private-converter-token'),converter_config=replace(config,root=tmp_path/'other'))
    with TestClient(app) as client:
        assert not client.get('/v1/capabilities',headers=HEADERS).json()['ocr_available']
        assert submit(client,scan(),ocr_enabled='true').json()['error']['code']=='OCR_UNAVAILABLE'


def test_missing_models_and_language_validation(tmp_path):
    config=ConverterConfig(root=tmp_path/'spool',ocr_models_dir=str(tmp_path/'missing'))
    app=create_app('converter',Settings(tmp_path/'archive','private-converter-token'),converter_config=config)
    with TestClient(app) as client:
        assert not client.get('/v1/capabilities',headers=HEADERS).json()['ocr_available']
        assert submit(client,scan(),ocr_enabled='true').json()['error']['code']=='OCR_UNAVAILABLE'


@pytest.mark.parametrize('limit,expected', [('max_image_pixels','IMAGE_PIXEL_LIMIT'),('max_ocr_pages','OCR_PAGE_LIMIT')])
def test_resource_bounds(tmp_path,limit,expected):
    config=replace(ConverterConfig(root=tmp_path/'spool'),**{limit:1})
    job,_,_=run(tmp_path,scan('TIFF',pages=2),config=config,ocr_enabled='true',generate_preview='false')
    assert job['status']=='failed' and job['error']['error']['code']==expected,job


def test_blank_ocr_reports_no_text(tmp_path):
    image=Image.new('RGB',(500,500),'white');data=BytesIO();image.save(data,format='PNG')
    job,result,_=run(tmp_path,data.getvalue(),ocr_enabled='true',generate_preview='false')
    assert job['status']=='completed',job
    assert result['extraction']['ocr_used'] and not result['extraction']['text_available']
    assert 'OCR_NO_TEXT_DETECTED' in result['warnings']


def test_preview_false_and_text_layer_never_run_ocr(tmp_path):
    from format_samples import pdf
    job,result,assets=run(tmp_path,pdf(pages=1),ocr_enabled='true',generate_preview='false')
    assert job['status']=='completed',job
    assert not result['extraction']['ocr_used'] and result['extraction']['ocr_languages']==[]
    assert all(a['kind']!='thumbnail' for a,_ in assets)


def test_encrypted_pdf_preview_preserves_error(tmp_path):
    from format_samples import pdf
    job,_,_=run(tmp_path,pdf(encrypted=True))
    assert job['status']=='failed' and job['error']['error']['code']=='PDF_PASSWORD_REQUIRED'


def test_image_without_ocr_or_preview_has_no_rendered_asset(tmp_path):
    job,result,assets=run(tmp_path,scan(),generate_preview='false')
    assert job['status']=='completed',job
    assert not result['extraction']['ocr_used'] and not result['extraction']['text_available']
    assert not any(a['kind']=='thumbnail' for a,_ in assets)


def test_partial_model_capability_and_admin_boolean(tmp_path,monkeypatch):
    import shutil
    from juanzhan.conversion_raster import available_languages
    target=tmp_path/'models';target.mkdir()
    shutil.copyfile(Path(ConverterConfig().ocr_models_dir)/'eng.traineddata',target/'eng.traineddata')
    config=ConverterConfig(root=tmp_path/'spool',ocr_models_dir=str(target))
    app=create_app('converter',Settings(tmp_path/'archive','private-converter-token'),converter_config=config)
    with TestClient(app) as client:
        assert client.get('/v1/capabilities',headers=HEADERS).json()['ocr_languages']==['eng']
        response=submit(client,scan(),ocr_enabled='true',ocr_languages='chi_sim')
        assert response.status_code==422 and response.json()['error']['code']=='OCR_LANGUAGE_UNAVAILABLE'
    monkeypatch.setenv('CONVERTER_ENABLE_OCR','false')
    assert not ConverterConfig.from_env().enable_ocr
    monkeypatch.setenv('CONVERTER_ENABLE_OCR','unexpected')
    with pytest.raises(ValueError):ConverterConfig.from_env()


def test_corrupt_model_not_advertised(tmp_path):
    from juanzhan.conversion_raster import available_languages
    (tmp_path/'eng.traineddata').write_bytes(b'corrupt')
    assert available_languages(str(tmp_path))==()


def test_real_ocr_request_deadline_cleans_inputs(tmp_path):
    config=ConverterConfig(root=tmp_path/'spool',wall_seconds=.00001)
    job,_,_=run(tmp_path,scan(),config=config,ocr_enabled='true')
    assert job['status']=='failed' and job['error']['error']['code']=='CONVERSION_TIMEOUT'
    assert not (config.root/job['job_id']/'input').exists()


def test_corrupt_image_fails_without_assets(tmp_path):
    job,result,assets=run(tmp_path,b'\x89PNG\r\n\x1a\nnot-an-image',ocr_enabled='true')
    assert job['status']=='failed' and result is None and not assets
    assert not (tmp_path/'spool'/job['job_id']/'input').exists()
