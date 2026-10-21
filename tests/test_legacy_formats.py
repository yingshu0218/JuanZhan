"""Legacy formats run actual libraries/binaries, never parser mocks."""
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import pytest
from test_parsing import pipeline
from test_format_acceptance import process
from juanzhan.uploads import sniff

@pytest.mark.parametrize('data,expected',[
    (b'{\\rtf1\\ansi Real RTF paragraph.\\par Next line.}','Real RTF paragraph.'),
    (b'{\\rtf1\\ansi\\ansicpg1252 \\u20013?\\u25991? \\par Budget 1980.0000}','中文'),
    (b'{\\rtf1\\ansi emoji \\u-10179?\\u-8704?}','😀'),
    (b'{\\rtf1\\ansi {\\field{\\*\\fldinst HYPERLINK "https://example.invalid"}{\\fldrslt Visible label}}}','Visible label'),
])
def test_rtf_plain_unicode_and_link_labels_without_active_instructions(pipeline,data,expected):
    _,_,summary=process(pipeline,data,'document.rtf')
    assert expected in str(summary['points'])
    assert 'https://example.invalid' not in str(summary['points'])
    assert 'RTF_FORMATTING_AND_EMBEDDED_OBJECTS_OMITTED' in summary['warnings']

@pytest.mark.parametrize('data',[b'{\\rtf1 unclosed',b'{\\rtf1 } extra}',b'{\\rtf1 '+b'{'*130+b'x'+b'}'*131,b'{\\rtf1 \\u-10179?}'])
def test_rtf_invalid_or_excessive_nesting_does_not_generate_success(pipeline,data):
    _,_,summary=process(pipeline,data,'broken.rtf','failed')
    assert not summary['points']

def test_cfb_headers_are_bounded_before_directory_parsing(pipeline):
    data=bytes.fromhex('d0cf11e0a1b11ae1')+b'\xff'*504
    assert sniff(BytesIO(data),'fake.doc')=='application/x-ole-storage'
    process(pipeline,data,'fake.doc','unsupported')

def test_csv_cells_containing_html_remain_literal_table_values(pipeline):
    data=b'kind,value\nhtml,"<html><body>literal</body></html>"\n'
    saved,_,_=process(pipeline,data,'literal.csv')
    body=pipeline[1].get('/api/v1/documents/'+saved['document_id']+'/content').json()['body']
    assert body[1]['structure']['table']['rows']==[['html','<html><body>literal</body></html>']]

def test_pinned_real_rtf_is_extracted_and_original_retained(pipeline):
    directory=os.environ.get('JUANZHAN_EXTRA_FORMAT_FIXTURES')
    if not directory:pytest.skip('Set JUANZHAN_EXTRA_FORMAT_FIXTURES to pinned Apache Tika fixtures')
    root=Path(directory);data=(root/'testRTF.rtf').read_bytes()
    entry=next(item for item in json.loads((root/'manifest.json').read_text()) if item['name']=='testRTF.rtf')
    assert hashlib.sha256(data).hexdigest()==entry['sha256']
    _,_,summary=process(pipeline,data,'real.rtf')
    assert summary['points'] and summary['text_available']

@pytest.mark.parametrize('name,expected',[
    ('testWORD_protected_passtika.doc','failed'),('testPPT_protected_passtika.ppt','failed'),('testEXCEL_protected_passtika.xls','failed'),
    ('testWORD_macros.doc','completed'),('testPPT_macros.ppt','completed'),('testEXCEL_macro.xls','completed'),
    ('testWORD_various.doc','completed'),('testPPT_various.ppt','completed'),('testRTFUnicodeGothic.rtf','completed'),
])
def test_pinned_legacy_encryption_macros_and_international_text(pipeline,name,expected):
    directory=os.environ.get('JUANZHAN_EXTRA_FORMAT_FIXTURES')
    if not directory:pytest.skip('Set JUANZHAN_EXTRA_FORMAT_FIXTURES to pinned Apache Tika fixtures')
    root=Path(directory);data=(root/name).read_bytes()
    entry=next(item for item in json.loads((root/'manifest.json').read_text()) if item['name']==name)
    assert hashlib.sha256(data).hexdigest()==entry['sha256']
    saved,_,summary=process(pipeline,data,name,expected)
    if expected=='completed':assert summary['points'] and summary['text_available']
    else:assert not summary['points']
    if name=='testWORD_various.doc':
        body=pipeline[1].get('/api/v1/documents/'+saved['document_id']+'/content').json()['body']
        text=''.join(block['text'] for block in body)
        assert any(0x4e00<=ord(c)<=0x9fff for c in text)
        assert any(ord(c)>0xffff for c in text)
        assert 'LEGACY_UTF16_SURROGATES_NORMALIZED' in summary['warnings']
    if name=='testPPT_various.ppt':
        body=pipeline[1].get('/api/v1/documents/'+saved['document_id']+'/content').json()['body']
        text=''.join(block['text'] for block in body)
        assert 'Gothic' in text and 'Bullet' in text and 'Row 1' in text
        assert any(ord(char)>0xffff for char in text)
        assert 'PPT_SPEAKER_NOTES_INCLUDED' in summary['warnings']

@pytest.mark.parametrize('corruption',['edit_cycle','out_of_bounds'])
def test_ppt_current_edit_chain_bounds_reject_corrupt_real_containers(pipeline,corruption):
    import olefile
    directory=os.environ.get('JUANZHAN_FORMAT_FIXTURES')
    if not directory:pytest.skip('Set JUANZHAN_FORMAT_FIXTURES to pinned Apache POI files')
    data=BytesIO((Path(directory)/'sample.ppt').read_bytes())
    with olefile.OleFileIO(data,write_mode=True) as package:
        user=bytearray(package.openstream('Current User').read())
        stream=bytearray(package.openstream('PowerPoint Document').read())
        offset=int.from_bytes(user[16:20],'little')
        if corruption=='edit_cycle':
            stream[offset+16:offset+20]=offset.to_bytes(4,'little')
            package.write_stream('PowerPoint Document',bytes(stream))
        else:
            user[16:20]=(len(stream)+100).to_bytes(4,'little')
            package.write_stream('Current User',bytes(user))
    _,_,summary=process(pipeline,data.getvalue(),'corrupt.ppt','failed')
    assert not summary['points']
