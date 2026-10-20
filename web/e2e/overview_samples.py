"""Synthetic cross-format documents for overview acceptance, never user files."""
import json
from pathlib import Path
import sys
from io import BytesIO
from xml.sax.saxutils import escape
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tests'))
from format_samples import zipped, epub, raster_sample


def word(sections):
    w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    paragraphs=[]
    for kind,text in sections:
        style=f'<w:pPr><w:pStyle w:val="Heading{kind}"/></w:pPr>' if kind else ''
        paragraphs.append(f'<w:p>{style}<w:r><w:t>{escape(text)}</w:t></w:r></w:p>')
    return zipped({'[Content_Types].xml':'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>',
        '_rels/.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        'word/document.xml':f'<w:document xmlns:w="{w}"><w:body>'+''.join(paragraphs)+'</w:body></w:document>',
        'word/styles.xml':f'<w:styles xmlns:w="{w}">'+''.join(f'<w:style w:styleId="Heading{i}"><w:pPr><w:outlineLvl w:val="{i-1}"/></w:pPr></w:style>' for i in (1,2,3))+'</w:styles>'})


def report_pdf():
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
    writer=PdfWriter()
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    for text in ['Quarterly report. Migration completed for three services.','Risk: legacy records need sampling. Budget: 1980 USD.','Next step: finish acceptance checks by Friday.']:
        page=writer.add_blank_page(width=612,height=792)
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        stream=DecodedStreamObject();stream.set_data(f'BT /F1 12 Tf 40 720 Td ({text}) Tj ET'.encode())
        page[NameObject('/Contents')]=writer._add_object(stream)
    result=BytesIO();writer.write(result);return result.getvalue()


def main():
    target=Path(sys.argv[1]);target.mkdir(parents=True,exist_ok=True)
    cases=[]
    def add(name,mime,body,expected,**options):
        (target/name).write_bytes(body if isinstance(body,bytes) else body.encode())
        cases.append(dict(name=name,mime=mime,expected=expected,**options))
    add('课程说明.docx','application/vnd.openxmlformats-officedocument.wordprocessingml.document',word([(1,'摄影课程说明'),(0,'学习拍摄、布光和后期处理。'),(2,'课程内容'),(3,'拍摄基础'),(0,'掌握曝光和构图。'),(3,'后期处理'),(0,'完成色彩与画面调整。'),(2,'学习安排'),(0,'6节直播课，12小时，1980元。')]),['拍摄基础','后期处理','1980元'])
    add('服务合同.docx','application/vnd.openxmlformats-officedocument.wordprocessingml.document',word([(1,'服务合同'),(2,'服务范围'),(0,'乙方交付网站设计及接口开发。'),(2,'付款与验收'),(0,'合同金额：30000元，验收后支付尾款。'),(2,'违约处理'),(0,'注意：延期应书面通知并协商处理。')]),['服务范围','30000元','延期'])
    add('会议纪要.txt','text/plain','本次会议确认接口迁移方案。\n\n王明负责回归测试。\n\n交付时间：周五提交验收报告。\n\n注意：原有数据必须完整保留。',['迁移方案','王明','周五','原有数据'])
    add('项目计划.md','text/markdown','# 项目计划\n\n## 当前进展\n\n已完成接口迁移。\n\n## 下一步\n\n- 完成移动端验收\n- 整理部署记录\n\n## 风险\n\n注意：旧版本数据需要抽查。',['接口迁移','移动端验收','部署记录','旧版本数据'])
    add('设备清单.html','text/html','<html><body><h1>设备清单</h1><table><tr><th>设备</th><th>状态</th></tr><tr><td>主机</td><td>已验收</td></tr><tr><td>路由器</td><td>待验证</td></tr></table></body></html>',['主机','已验收','路由器','待验证'])
    add('操作手册.epub','application/epub+zip',epub(),['第一章','书籍第一段','第二章','书籍第二段'])
    add('季度报告.pdf','application/pdf',report_pdf(),['Quarterly report','Migration','legacy records','Friday'])
    add('长篇笔记.txt','text/plain','\n\n'.join(f'第{i:03d}条记录：项目进展及验收结论。' for i in range(1,121)),['第001条'],partial=True)
    add('扫描报告.pdf','application/pdf',raster_sample('PDF',text='Scanned report without OCR'),[],empty=True)
    add('安全网页.html','text/html','<html><body><h1>处理说明</h1><p>重要：保留原始文件。</p><script>window.OVERVIEW_ATTACK=true</script><img src="https://invalid.example/tracker"/><p>&lt;script&gt;test&lt;/script&gt;</p></body></html>',['保留原始文件'])
    (target/'manifest.json').write_text(json.dumps(cases,ensure_ascii=False))
if __name__=='__main__':main()
