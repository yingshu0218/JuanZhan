"""Real package bytes through HTTP, worker, SQLite, storage and shared overview."""
import pytest
import os
import json
import hashlib
from pathlib import Path
from format_samples import zipped
from test_format_acceptance import process
from test_parsing import pipeline
from juanzhan.conversion_office import XLSX,PPTX,ODT,ODS,ODP

S='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
P='http://schemas.openxmlformats.org/presentationml/2006/main'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'

def workbook(rows=None,target='worksheets/sheet2.xml',external=False):
    return zipped({'[Content_Types].xml':'<Types/>',
        'xl/workbook.xml':f'<workbook xmlns="{S}" xmlns:r="{R}"><sheets><sheet name="采购清单" sheetId="2" r:id="r2"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels':f'<Relationships><Relationship Id="r2" Type="{R}/worksheet" Target="{target}"'+(' TargetMode="External"' if external else '')+'/></Relationships>',
        'xl/worksheets/sheet2.xml':f'<worksheet xmlns="{S}"><sheetData>'+(rows or '<row r="1"><c r="A1" t="inlineStr"><is><t>设备</t></is></c><c r="B1" t="inlineStr"><is><t>状态</t></is></c></row><row r="3"><c r="A3" t="inlineStr"><is><t>主机已验收</t></is></c><c r="B3"><f>SUM(1,2)</f><v>3</v></c></row>')+'</sheetData></worksheet>'})

def presentation():
    return zipped({'[Content_Types].xml':'<Types/>',
        'ppt/presentation.xml':f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst><p:sldId id="300" r:id="r2"/><p:sldId id="301" r:id="r1"/></p:sldIdLst></p:presentation>',
        'ppt/_rels/presentation.xml.rels':f'<Relationships><Relationship Id="r1" Type="{R}/slide" Target="slides/slide1.xml"/><Relationship Id="r2" Type="{R}/slide" Target="slides/slide2.xml"/></Relationships>',
        **{'ppt/slides/slide'+str(i)+'.xml':f'<p:sld xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>' for i,text in ((1,'第二部分：本月安排'),(2,'第一部分：项目验收'))}})

def odf(mime,body=None):
    kind={ODT:'text',ODS:'spreadsheet',ODP:'presentation'}[mime]
    if body is None:
        if mime==ODS:body='<table:table table:name="采购清单"><table:table-row><table:table-cell><text:p>主机已验收</text:p></table:table-cell><table:table-cell office:value="1980.00"/></table:table-row></table:table>'
        elif mime==ODP:body='<draw:page draw:name="项目规划"><draw:frame><draw:text-box><text:p>完成项目验收</text:p></draw:text-box></draw:frame></draw:page>'
        else:body='<text:h text:outline-level="1">项目规划</text:h><text:p>完成项目验收</text:p>'
    return zipped({'mimetype':mime,'content.xml':f'<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"><office:body><office:{kind}>{body}</office:{kind}></office:body></office:document-content>'})

@pytest.mark.parametrize('ext,data,expected',[
    ('xlsx',workbook(),'主机已验收'),('pptx',presentation(),'项目验收'),
    ('odt',odf(ODT),'项目验收'),('ods',odf(ODS),'主机已验收'),('odp',odf(ODP),'项目验收')])
def test_new_office_families_have_persisted_source_backed_overviews(pipeline,ext,data,expected):
    saved,_,summary=process(pipeline,data,'document.'+ext)
    assert summary['points'] and expected in str(summary['points'])
    client=pipeline[1]
    content=client.get('/api/v1/documents/'+saved['document_id']+'/content').json()
    assert content['body'] and all(block['confidence'] is None for block in content['body'])
    assert all(block['locator']['kind']!='page' for block in content['body'])
    if ext=='xlsx':
        assert 'FORMULAS_NOT_EVALUATED_CACHED_VALUES_ONLY' in summary['warnings']
        assert '行 3' in str(content['body']) and 'SUM' not in str(content['body'])
    if ext=='pptx':
        text=' '.join(block['text'] for block in content['body'])
        assert text.index('第一部分')<text.index('第二部分')

@pytest.mark.parametrize('data',[
    workbook(target='https://example.invalid/remote',external=True),
    workbook(target='../../../outside.xml'),
    workbook(rows='<row r="1"><c r="XFD1"><v>7</v></c></row>'),
    workbook(rows='<row r="1"><c r="A2"><v>7</v></c></row>'),
    odf(ODS,'<table:table table:name="bad"><table:table-row table:number-rows-repeated="1048577"><table:table-cell><text:p>x</text:p></table:table-cell></table:table-row></table:table>'),
])
def test_package_external_traversal_and_expansion_rejected_without_original_loss(pipeline,data):
    _,_,summary=process(pipeline,data,'untrusted.bin','failed')
    assert not summary['points']

@pytest.mark.parametrize('kind,cache',[('n',''),('b','<v/>'),('s','<v/>')])
def test_missing_formula_cache_is_not_a_computed_zero(pipeline,kind,cache):
    saved,_,summary=process(pipeline,workbook(rows='<row r="1"><c r="A1" t="inlineStr"><is><t>预算</t></is></c><c r="B1" t="'+kind+'"><f>1+1</f>'+cache+'</c></row>'),'formula.xlsx')
    assert 'FORMULA_CACHE_MISSING' in summary['warnings']
    body=pipeline[1].get('/api/v1/documents/'+saved['document_id']+'/content').json()['body']
    assert body[1]['structure']['table']['rows']==[['预算','']]

def test_odf_repeated_cells_and_rows_keep_exact_values(pipeline):
    data=odf(ODS,'<table:table table:name="预算"><table:table-row table:number-rows-repeated="2"><table:table-cell office:value="9007199254740993" table:number-columns-repeated="2"/><table:table-cell table:formula="of:=1+1"/></table:table-row></table:table>')
    saved,_,summary=process(pipeline,data,'budget.ods')
    body=pipeline[1].get('/api/v1/documents/'+saved['document_id']+'/content').json()['body']
    assert body[1]['structure']['table']['rows']==[['9007199254740993','9007199254740993']]
    assert body[2]['structure']['table']['rows']==body[1]['structure']['table']['rows']
    assert body[1]['locator']!=body[2]['locator']
    assert 'FORMULA_CACHE_MISSING' in summary['warnings']

@pytest.mark.parametrize('extension,encoding,source,expected',[
    ('csv','utf-8','设备,金额\n"主机,备机",1980.0000\n',['主机,备机','1980.0000']),
    ('csv','utf-16','设备;备注\n主机;"第一行\n第二行"\n',['主机','第一行\n第二行']),
    ('tsv','utf-8','设备\t公式\n主机\t=HYPERLINK("https://example.invalid")\n',['主机','=HYPERLINK("https://example.invalid")']),
])
def test_delimited_tables_preserve_quoted_newlines_exact_numbers_and_literal_formulas(pipeline,extension,encoding,source,expected):
    saved,_,summary=process(pipeline,source.encode(encoding),'sample.'+extension)
    body=pipeline[1].get('/api/v1/documents/'+saved['document_id']+'/content').json()['body']
    assert body[1]['structure']['table']['rows']==[expected]
    assert 'DELIMITED_VALUES_ARE_TEXT_NO_FORMULA_EXECUTION' in summary['warnings']

@pytest.mark.parametrize('name',['LibreOfficeCalc_ods_1.3.ods','LibreOfficeImpress_odp_1.3.odp','LibreOfficeWriter_odt_1.3.odt'])
def test_pinned_real_libreoffice_documents(pipeline,name):
    directory=os.environ.get('JUANZHAN_EXTRA_FORMAT_FIXTURES')
    if not directory:pytest.skip('Set JUANZHAN_EXTRA_FORMAT_FIXTURES to pinned Apache Tika fixtures')
    root=Path(directory);data=(root/name).read_bytes()
    expected=next(item for item in json.loads((root/'manifest.json').read_text()) if item['name']==name)
    assert hashlib.sha256(data).hexdigest()==expected['sha256']
    assert len(data)==expected['size_bytes']
    _,_,summary=process(pipeline,data,name)
    assert summary['points'] and summary['text_available']
