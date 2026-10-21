"""Legacy Office/RTF extraction inside the existing resource-limited parser process."""
from io import BytesIO, StringIO
from pathlib import Path
import os
import re
import subprocess
import tempfile
from .conversion_formats import FormatError
from .conversion_office import table

DOC='application/msword'
XLS='application/vnd.ms-excel'
PPT='application/vnd.ms-powerpoint'
RTF='application/rtf'
LEGACY_TYPES=[DOC,XLS,PPT,RTF]

def tool_text(data,out,command):
    executable=Path('/usr/bin')/command
    if not executable.is_file():raise FormatError('LEGACY_TOOL_UNAVAILABLE')
    with tempfile.TemporaryDirectory(prefix='juanzhan-legacy-') as temp:
        source=Path(temp)/'original';source.write_bytes(data)
        with tempfile.TemporaryFile() as output:
            try:
                process=subprocess.run([str(executable),'-d','utf-8',str(source)],stdout=output,stderr=subprocess.DEVNULL,
                    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},timeout=20,check=False)
            except subprocess.TimeoutExpired:raise FormatError('LEGACY_CONVERSION_TIMEOUT') from None
            if process.returncode:
                raise FormatError('LEGACY_RESOURCE_LIMIT' if process.returncode<0 else 'INVALID_LEGACY_DOCUMENT')
            if output.tell()>out.limits['max_output_bytes']:raise FormatError('RESULT_LIMIT')
            output.seek(0)
            try:
                text=output.read(out.limits['max_output_bytes']+1).decode('utf-8','surrogatepass')
                if any(0xd800<=ord(char)<=0xdfff for char in text):out.warn('LEGACY_UTF16_SURROGATES_NORMALIZED')
                return text.encode('utf-16-le','surrogatepass').decode('utf-16-le')
            except UnicodeError:raise FormatError('LEGACY_TEXT_ENCODING') from None

def legacy_text(data,out,mime):
    if mime==DOC:
        import olefile
        with olefile.OleFileIO(BytesIO(data)) as package:
            header=package.openstream('WordDocument').read(12)
        if len(header)<12:raise FormatError('INVALID_LEGACY_DOCUMENT')
        if int.from_bytes(header[10:12],'little')&0x8100:raise FormatError('OFFICE_PASSWORD_REQUIRED')
    out.parser='catdoc'
    text=tool_text(data,out,out.parser)
    # Tool output cannot prove original page/slide positions or reconstruct table geometry.
    text=re.sub(r'[\x00-\x08\x0b\x0e-\x1f]','',text)
    for paragraph in re.split(r'\n\s*\n|\f',text):
        if paragraph.strip():out.prose(paragraph.strip(),{'kind':'unknown'})
    out.warn('LEGACY_LAYOUT_TABLES_AND_LOCATORS_UNAVAILABLE')
    out.warn('MACROS_EMBEDDED_OBJECTS_AND_LINKS_NOT_EXECUTED')

def xls_format(data,out):
    import xlrd
    out.parser='xlrd'
    try:
        book=xlrd.open_workbook(file_contents=data,on_demand=True,ragged_rows=True,logfile=StringIO())
        try:
            for index in range(book.nsheets):
                sheet=book.sheet_by_index(index)
                name=sheet.name
                if sheet.nrows>100000 or sheet.ncols>256:raise FormatError('SPREADSHEET_CELL_LIMIT')
                out.add('heading',name,{'kind':'section','heading_path':[name]},level=1)
                cells=0
                for row in range(sheet.nrows):
                    values=[]
                    for cell in sheet.row(row):
                        cells+=1
                        if cells>100000:raise FormatError('SPREADSHEET_CELL_LIMIT')
                        if cell.ctype in (xlrd.XL_CELL_EMPTY,xlrd.XL_CELL_BLANK):value=''
                        elif cell.ctype==xlrd.XL_CELL_BOOLEAN:value='true' if cell.value else 'false'
                        elif cell.ctype==xlrd.XL_CELL_ERROR:
                            value=xlrd.error_text_from_code.get(cell.value,'#ERROR');out.warn('SOURCE_CELL_ERRORS_PRESENT')
                        elif cell.ctype==xlrd.XL_CELL_DATE:
                            value=xlrd.xldate_as_datetime(cell.value,book.datemode).isoformat();out.warn('EXCEL_DATE_VALUES_DECODED')
                        elif cell.ctype==xlrd.XL_CELL_NUMBER:
                            value=str(int(cell.value)) if cell.value.is_integer() else repr(cell.value)
                        else:value=str(cell.value)
                        values.append(value)
                    if any(values):table(out,[values],[name,'行 '+str(row+1)])
                book.unload_sheet(index)
        finally:book.release_resources()
    except FormatError:raise
    except Exception:raise FormatError('INVALID_OR_PROTECTED_XLS') from None
    out.warn('FORMULAS_NOT_EVALUATED_CACHED_VALUES_ONLY')
    out.warn('BIFF_NUMBERS_HAVE_SOURCE_FLOAT_PRECISION')
    out.warn('SPREADSHEET_LAYOUT_NOT_PRESERVED')

def rtf_format(data,out):
    from striprtf.striprtf import rtf_to_text
    out.parser='striprtf'
    # RTF is ASCII control syntax with legacy codepage bytes and signed Unicode escapes.
    source=data.decode('latin-1')
    if not source.lstrip().startswith('{\\rtf'):raise FormatError('INVALID_RTF')
    depth=0;maximum=0
    # Bound nesting before the library allocates its destination stack. Escaped braces are literals.
    for match in re.finditer(r'\\.|[{}]',source,re.S):
        if match[0]=='{':depth+=1;maximum=max(maximum,depth)
        elif match[0]=='}':
            depth-=1
            if depth<0:raise FormatError('INVALID_RTF')
    if depth or maximum>128:raise FormatError('INVALID_RTF')
    try:
        text=rtf_to_text(source,encoding='cp1252',errors='strict')
        # RTF \u controls encode UTF-16 units; join valid pairs and reject lone surrogates.
        text=text.encode('utf-16-le','surrogatepass').decode('utf-16-le')
    except (UnicodeError,ValueError,IndexError):raise FormatError('INVALID_RTF') from None
    for paragraph in re.split(r'\n\s*\n|\f',text):
        if paragraph.strip():out.prose(paragraph.strip(),{'kind':'unknown'})
    out.warn('RTF_FORMATTING_AND_EMBEDDED_OBJECTS_OMITTED')
