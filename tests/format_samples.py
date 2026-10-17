"""Small valid binary documents generated from their public formats, never fake parse JSON."""
from io import BytesIO
import zipfile


def zipped(items, compression=zipfile.ZIP_DEFLATED):
    output=BytesIO()
    with zipfile.ZipFile(output,'w',compression=compression) as package:
        for name,content in items.items():package.writestr(name,content)
    return output.getvalue()


def docx():
    w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    return zipped({
        '[Content_Types].xml':'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>',
        '_rels/.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        'word/document.xml':f'''<w:document xmlns:w="{w}"><w:body>
<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>项目规划</w:t></w:r></w:p>
<w:p><w:r><w:t>真实 Word 正文。</w:t><w:tab/><w:t>保留文本</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="Bullet"/></w:pPr><w:r><w:t>清单项目</w:t></w:r></w:p>
<w:tbl><w:tr><w:trPr><w:tblHeader/></w:trPr><w:tc><w:p><w:r><w:t>字段</w:t></w:r></w:p></w:tc></w:tr>
<w:tr><w:tc><w:p><w:r><w:t>内容</w:t></w:r></w:p></w:tc></w:tr></w:tbl><w:sectPr/>
</w:body></w:document>''',
        'word/styles.xml':f'<w:styles xmlns:w="{w}"><w:style w:styleId="Heading1"><w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style><w:style w:styleId="Bullet"><w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr></w:style></w:styles>',
        'docProps/core.xml':'<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>真实标题</dc:title><dc:creator>测试作者</dc:creator></cp:coreProperties>'})


def epub():
    return zipped({
        'mimetype':'application/epub+zip',
        'META-INF/container.xml':'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        'OEBPS/content.opf':'<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>电子书</dc:title><dc:creator>书籍作者</dc:creator><dc:language>zh</dc:language></metadata><manifest><item id="second" href="second.xhtml" media-type="application/xhtml+xml"/><item id="first" href="first.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="first"/><itemref idref="second"/></spine></package>',
        'OEBPS/first.xhtml':'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>首章</title></head><body><h1>第一章</h1><p>书籍第一段。</p></body></html>',
        'OEBPS/second.xhtml':'<html xmlns="http://www.w3.org/1999/xhtml"><body><h2>第二章</h2><p>书籍第二段。</p></body></html>'})


def pdf(blank=False, encrypted=False, pages=2):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject, ArrayObject, NumberObject
    writer=PdfWriter()
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    for index in range(pages):
        page=writer.add_blank_page(width=612,height=792)
        if not blank:
            page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
            stream=DecodedStreamObject()
            stream.set_data(f'BT /F1 12 Tf 72 720 Td (Real PDF page {index+1}) Tj ET'.encode())
            page[NameObject('/Contents')]=writer._add_object(stream)
    writer.add_metadata({'/Title':'Actual PDF title','/Author':'Actual author'})
    if encrypted:writer.encrypt('secret')
    output=BytesIO();writer.write(output)
    return output.getvalue()


def samples():
    return {
        'txt':('text/plain','纯文本第一段。\n\n第二段。\n'.encode()),
        'md':('text/markdown','# 资料标题\n\n正文 **强调** 与 [链接](https://example.invalid)。\n\n- 第一项\n- 第二项\n\n| 字段 | 数值 |\n| --- | --- |\n| 金额 | 2.00 |\n'.encode()),
        'html':('text/html','<!doctype html><html lang="zh"><head><title>网页标题</title><meta name="author" content="网页作者"/></head><body><h1>网页资料</h1><p>可读正文<strong>加粗</strong>。</p><ul><li>网页条目</li></ul><table><tr><th>列名</th></tr><tr><td>单元格</td></tr></table><script>NEVER_EXECUTE</script><p hidden>HIDDEN_SECRET</p><img src="https://example.invalid/track" alt="图片说明"/></body></html>'.encode()),
        'docx':('application/vnd.openxmlformats-officedocument.wordprocessingml.document',docx()),
        'epub':('application/epub+zip',epub()),
        'pdf':('application/pdf',pdf()),
    }


def chinese_pdf():
    from pypdf import PdfWriter
    from pypdf.generic import (DictionaryObject,NameObject,DecodedStreamObject,ArrayObject,
                              NumberObject,TextStringObject)
    writer=PdfWriter();page=writer.add_blank_page(width=612,height=792)
    descriptor=DictionaryObject({NameObject('/Type'):NameObject('/FontDescriptor'),NameObject('/FontName'):NameObject('/STSong-Light'),NameObject('/Flags'):NumberObject(6),NameObject('/FontBBox'):ArrayObject([NumberObject(n) for n in (-25,-254,1000,880)]),NameObject('/ItalicAngle'):NumberObject(0),NameObject('/Ascent'):NumberObject(752),NameObject('/Descent'):NumberObject(-271),NameObject('/CapHeight'):NumberObject(737),NameObject('/StemV'):NumberObject(58)})
    descendant=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/CIDFontType0'),NameObject('/BaseFont'):NameObject('/STSong-Light'),NameObject('/CIDSystemInfo'):DictionaryObject({NameObject('/Registry'):TextStringObject('Adobe'),NameObject('/Ordering'):TextStringObject('GB1'),NameObject('/Supplement'):NumberObject(4)}),NameObject('/FontDescriptor'):writer._add_object(descriptor),NameObject('/DW'):NumberObject(1000)})
    cmap=DecodedStreamObject();cmap.set_data(b'/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def /CMapName /Unicode def /CMapType 2 def 1 begincodespacerange <0000> <FFFF> endcodespacerange 1 beginbfrange <0000> <FFFF> <0000> endbfrange endcmap CMapName currentdict /CMap defineresource pop end end')
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type0'),NameObject('/BaseFont'):NameObject('/STSong-Light'),NameObject('/Encoding'):NameObject('/UniGB-UCS2-H'),NameObject('/DescendantFonts'):ArrayObject([writer._add_object(descendant)]),NameObject('/ToUnicode'):writer._add_object(cmap)})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
    stream=DecodedStreamObject();stream.set_data(('BT /F1 12 Tf 72 720 Td <'+'中文资料'.encode('utf-16-be').hex()+'> Tj ET').encode())
    page[NameObject('/Contents')]=writer._add_object(stream)
    result=BytesIO();writer.write(result);return result.getvalue()


def raster_sample(format='PNG',text='Real scanned archive 2026',pages=1):
    from PIL import Image, ImageDraw, ImageFont
    image=Image.new('RGB',(1600,500),'white')
    font=ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',58)
    ImageDraw.Draw(image).text((60,160),text,font=font,fill='black')
    result=BytesIO()
    if format in ('PDF','TIFF'):
        image.save(result,format=format,save_all=True,append_images=[image]*(pages-1),resolution=144,**({'compression':'tiff_lzw'} if format=='TIFF' else {}))
    else:image.save(result,format=format)
    return result.getvalue()
