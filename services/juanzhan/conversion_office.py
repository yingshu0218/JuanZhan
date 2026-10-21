"""Offline OOXML adapters. Stored values only: no formulas, macros or relationships run."""
import posixpath
import re
import csv
from io import StringIO
from .conversion_formats import SafeZip, FormatError, safe_href, decode, XLSX, PPTX, ODT, ODS, ODP, OFFICE_TYPES
S='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
P='{http://schemas.openxmlformats.org/presentationml/2006/main}'
A='{http://schemas.openxmlformats.org/drawingml/2006/main}'
R='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
O='{urn:oasis:names:tc:opendocument:xmlns:office:1.0}'
T='{urn:oasis:names:tc:opendocument:xmlns:text:1.0}'
B='{urn:oasis:names:tc:opendocument:xmlns:table:1.0}'
D='{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}'

def delimited_format(data,out,delimiter=None):
    out.parser='juanzhan-delimited-text'
    text=decode(data);csv.field_size_limit(65536)
    if delimiter is None:
        try:delimiter=csv.Sniffer().sniff(text[:8192],delimiters=',;\t|').delimiter
        except csv.Error:delimiter=','
    reader=csv.reader(StringIO(text,newline=''),delimiter=delimiter,strict=True)
    cells=0;width=None
    try:
        for index,row in enumerate(reader):
            cells+=len(row)
            if len(row)>256 or cells>100000:raise FormatError('SPREADSHEET_CELL_LIMIT')
            if width is not None and len(row)!=width:out.warn('DELIMITED_ROWS_HAVE_DIFFERENT_WIDTHS')
            width=len(row) if width is None else width
            if row:table(out,[row],['记录 '+str(index+1),'截至源文件行 '+str(reader.line_num)])
    except csv.Error:raise FormatError('INVALID_DELIMITED_TEXT') from None
    out.warn('DELIMITED_VALUES_ARE_TEXT_NO_FORMULA_EXECUTION')

def relationships(package,path):
    name=posixpath.join(posixpath.dirname(path),'_rels',posixpath.basename(path)+'.rels')
    result={}
    for item in package.xml(name):
        id=item.get('Id')
        if not id or id in result:raise FormatError('INVALID_PACKAGE_RELATIONSHIPS')
        result[id]=item
    return result

def target(item,path,kind):
    if item is None or item.get('TargetMode','Internal')!='Internal' or not item.get('Type','').endswith('/'+kind):
        raise FormatError('UNSAFE_PACKAGE_REFERENCE')
    href=item.get('Target','')
    # OOXML allows package-root absolute paths, unlike EPUB.
    if href.startswith('/') and not href.startswith('//'):href=href[1:];path=''
    return safe_href(path,href)

def table(out,rows,path):
    if not rows:return
    # Never guess which source row is a header. Small batches keep each source useful.
    for offset in range(0,len(rows),20):
        chunk=rows[offset:offset+20]
        out.add('table','\n'.join('\t'.join(row) for row in chunk),
                {'kind':'section','heading_path':path},table={'headers':[],'rows':chunk})

def xlsx_format(data,out):
    out.parser='juanzhan-xlsx-xml'
    with SafeZip(data,out.limits) as package:
        workbook='xl/workbook.xml';root=package.xml(workbook);rels=relationships(package,workbook)
        strings=[]
        for relation in rels.values():
            if relation.get('Type','').endswith('/sharedStrings'):
                for item in package.xml(target(relation,workbook,'sharedStrings')):
                    strings.append(''.join(t.text or '' for t in item.iter(S+'t')))
        sheets=root.find(S+'sheets')
        if sheets is None:raise FormatError('INVALID_PACKAGE')
        for sheet in sheets:
            name=sheet.get('name','');path=[name]
            if not name:raise FormatError('INVALID_PACKAGE')
            relation=rels.get(sheet.get(R+'id'))
            if relation is not None and not relation.get('Type','').endswith('/worksheet'):
                out.warn('NON_WORKSHEET_SHEET_OMITTED');continue
            xml=package.xml(target(relation,workbook,'worksheet'))
            out.add('heading',name,{'kind':'section','heading_path':path},level=1)
            if sheet.get('state','visible')!='visible':out.warn('HIDDEN_SHEETS_INCLUDED')
            last_row=0;cells=0
            for row in xml.findall(S+'sheetData/'+S+'row'):
                number=int(row.get('r',last_row+1))
                if not last_row<number<=1048576:raise FormatError('INVALID_SPREADSHEET_POSITION')
                last_row=number;values=[];last_col=0
                for cell in row.findall(S+'c'):
                    cells+=1
                    if cells>100000:raise FormatError('SPREADSHEET_CELL_LIMIT')
                    ref=cell.get('r')
                    if ref:
                        match=re.fullmatch(r'([A-Z]{1,3})([1-9][0-9]*)',ref)
                        if not match or int(match[2])!=number:raise FormatError('INVALID_SPREADSHEET_POSITION')
                        col=0
                        for letter in match[1]:col=col*26+ord(letter)-64
                    else:col=last_col+1
                    if not last_col<col<=256:raise FormatError('SPREADSHEET_COLUMN_LIMIT')
                    last_col=col;value=cell.findtext(S+'v','');kind=cell.get('t','n')
                    missing_cache=False
                    if cell.find(S+'f') is not None:
                        out.warn('FORMULAS_NOT_EVALUATED_CACHED_VALUES_ONLY')
                        missing_cache=cell.findtext(S+'v') in (None,'')
                        if missing_cache:out.warn('FORMULA_CACHE_MISSING')
                    if missing_cache:value=''
                    elif kind=='s':
                        index=int(value)
                        if not 0<=index<len(strings):raise FormatError('INVALID_SHARED_STRING')
                        value=strings[index]
                    elif kind=='inlineStr':value=''.join(t.text or '' for t in cell.iter(S+'t'))
                    elif kind=='b':
                        if value not in ('0','1'):raise FormatError('INVALID_SPREADSHEET_BOOLEAN')
                        value='true' if value=='1' else 'false'
                    elif kind not in ('n','str','e','d'):raise FormatError('INVALID_SPREADSHEET_CELL_TYPE')
                    if cell.get('s') is not None:out.warn('CELL_FORMATS_NOT_RENDERED_RAW_VALUES')
                    if kind=='e':out.warn('SOURCE_CELL_ERRORS_PRESENT')
                    values.extend(['']*(col-len(values)-1));values.append(value)
                if any(values):
                    # Locator includes actual row number, including sparse rows.
                    table(out,[values],[name,'行 '+str(number)])
            if xml.find(S+'mergeCells') is not None:out.warn('MERGED_CELLS_FLATTENED')
        out.warn('CHARTS_IMAGES_AND_COMMENTS_OMITTED')
        out.warn('SPREADSHEET_LAYOUT_NOT_PRESERVED')

def drawing_text(element):
    return ''.join(node.text or '' if node.tag==A+'t' else '\n' if node.tag==A+'br' else '\t' if node.tag==A+'tab' else '' for node in element.iter())

def pptx_format(data,out):
    out.parser='juanzhan-pptx-xml'
    with SafeZip(data,out.limits) as package:
        path='ppt/presentation.xml';root=package.xml(path);rels=relationships(package,path)
        slides=root.find(P+'sldIdLst')
        if slides is None:raise FormatError('INVALID_PACKAGE')
        for index,slide in enumerate(slides):
            if index>=out.limits['max_pages']:raise FormatError('PAGE_LIMIT')
            slide_path=target(rels.get(slide.get(R+'id')),path,'slide')
            xml=package.xml(slide_path)
            location={'kind':'section','heading_path':['幻灯片 '+str(index+1)]}
            out.add('heading',location['heading_path'][0],location,level=1)
            tree=xml.find(P+'cSld/'+P+'spTree')
            if tree is None:raise FormatError('INVALID_PACKAGE')
            # Iteration follows stored shape order; visual overlap/order is not inferred.
            for shape in tree.iter():
                if shape.tag==P+'sp':
                    holder=shape.find(P+'nvSpPr/'+P+'nvPr/'+P+'ph')
                    title=holder is not None and holder.get('type') in ('title','ctrTitle')
                    for paragraph in shape.findall(P+'txBody/'+A+'p'):
                        text=drawing_text(paragraph)
                        if text.strip():
                            if title:out.add('heading',text,location,level=2)
                            else:out.prose(text,location)
                elif shape.tag==A+'tbl':
                    rows=[[ '\n'.join(drawing_text(p) for p in cell.findall(A+'txBody/'+A+'p')) for cell in row.findall(A+'tc')] for row in shape.findall(A+'tr')]
                    table(out,rows,location['heading_path'])
            relpath=posixpath.join(posixpath.dirname(slide_path),'_rels',posixpath.basename(slide_path)+'.rels')
            if relpath in package.entries:
                for relation in relationships(package,slide_path).values():
                    if not relation.get('Type','').endswith('/notesSlide'):continue
                    notes=package.xml(target(relation,slide_path,'notesSlide'))
                    if notes.tag!=P+'notes':raise FormatError('INVALID_PACKAGE')
                    paragraphs=[drawing_text(p) for p in notes.findall('.//'+P+'sp/'+P+'txBody/'+A+'p')]
                    paragraphs=[text for text in paragraphs if text.strip()]
                    if paragraphs:
                        note_location={'kind':'section','heading_path':location['heading_path']+['备注']}
                        out.add('heading','备注',note_location,level=2)
                        for text in paragraphs:out.prose(text,note_location)
                        out.warn('SLIDE_SPEAKER_NOTES_INCLUDED')
        out.warn('SLIDE_SHAPE_ORDER_NOT_VISUAL_READING_ORDER')
        out.warn('SLIDE_CHARTS_IMAGES_AND_MEDIA_OMITTED')

def odf_text(element):
    parts=[]
    def walk(node):
        if node.tag==T+'s':
            count=int(node.get(T+'c','1'))
            if not 1<=count<=4096:raise FormatError('RESULT_LIMIT')
            parts.append(' '*count)
        elif node.tag==T+'tab':parts.append('\t')
        elif node.tag==T+'line-break':parts.append('\n')
        else:
            if node.text:parts.append(node.text)
            for child in node:walk(child)
        if node.tail:parts.append(node.tail)
    walk(element)
    return ''.join(parts)

def odf_format(data,out):
    out.parser='juanzhan-odf-xml'
    with SafeZip(data,out.limits) as package:
        mime=package.read('mimetype').decode('ascii')
        if mime not in (ODT,ODS,ODP):raise FormatError('INVALID_PACKAGE')
        root=package.xml('content.xml');body=root.find(O+'body')
        expected={ODT:'text',ODS:'spreadsheet',ODP:'presentation'}[mime]
        content=body.find(O+expected) if body is not None else None
        if content is None:raise FormatError('INVALID_PACKAGE')
        if mime==ODS:
            for sheet in content.findall(B+'table'):
                name=sheet.get(B+'name','')
                if not name:raise FormatError('INVALID_PACKAGE')
                out.add('heading',name,{'kind':'section','heading_path':[name]},level=1)
                number=0
                for row in sheet.iter(B+'table-row'):
                    repeat=int(row.get(B+'number-rows-repeated','1'))
                    if not 1<=repeat<=1048576:raise FormatError('SPREADSHEET_ROW_LIMIT')
                    values=[]
                    for cell in row:
                        if cell.tag not in (B+'table-cell',B+'covered-table-cell'):continue
                        copies=int(cell.get(B+'number-columns-repeated','1'))
                        paragraphs=[odf_text(p) for p in cell.findall(T+'p')]
                        value='\n'.join(paragraphs) if paragraphs else next((cell.get(O+key) for key in ('string-value','value','date-value','time-value','boolean-value') if cell.get(O+key) is not None),'')
                        if cell.get(B+'formula') is not None:
                            out.warn('FORMULAS_NOT_EVALUATED_CACHED_VALUES_ONLY')
                            if not value:out.warn('FORMULA_CACHE_MISSING')
                        if not 1<=copies<=16384:raise FormatError('SPREADSHEET_COLUMN_LIMIT')
                        if len(values)+copies>256:
                            if value:raise FormatError('SPREADSHEET_COLUMN_LIMIT')
                            copies=max(0,256-len(values))
                        values.extend([value]*copies)
                    while values and not values[-1]:values.pop()
                    if values:
                        if repeat>10000 or number+repeat>1048576:raise FormatError('SPREADSHEET_ROW_LIMIT')
                        for offset in range(repeat):table(out,[values],[name,'行 '+str(number+offset+1)])
                    number+=repeat
                    if number>1048576:raise FormatError('SPREADSHEET_ROW_LIMIT')
            out.warn('SPREADSHEET_LAYOUT_NOT_PRESERVED')
        else:
            containers=list(content.findall(D+'page')) if mime==ODP else [content]
            for index,container in enumerate(containers):
                if mime==ODP:
                    if index>=out.limits['max_pages']:raise FormatError('PAGE_LIMIT')
                    name=container.get(D+'name') or '幻灯片 '+str(index+1)
                    out.add('heading',name,{'kind':'section','heading_path':[name]},level=1)
                def visit(node,depth=0):
                    if depth>64:raise FormatError('RESULT_LIMIT')
                    if node.tag in (T+'p',T+'h'):
                        value=odf_text(node).strip()
                        if value:
                            if node.tag==T+'h':out.add('heading',value,level=min(6,max(1,int(node.get(T+'outline-level','1')))))
                            else:out.prose(value)
                    elif node.tag==B+'table':
                        rows=[['\n'.join(odf_text(p) for p in cell.findall(T+'p')) for cell in row if cell.tag in (B+'table-cell',B+'covered-table-cell')] for row in node.findall(B+'table-row')]
                        table(out,rows,list(out.heading_path))
                    elif node.tag not in (O+'scripts',O+'forms',T+'tracked-changes'):
                        for child in node:visit(child,depth+1)
                visit(container)
        out.warn('ODF_LAYOUT_EMBEDDED_OBJECTS_AND_TRACKED_CHANGES_OMITTED')
