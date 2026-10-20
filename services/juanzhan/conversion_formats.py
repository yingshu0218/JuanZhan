"""Bounded, offline format adapters. No extraction to disk or external resource loading."""
from dataclasses import dataclass
import html
from io import BytesIO
import posixpath
import re
import stat
from urllib.parse import unquote, urlsplit
import zipfile

from defusedxml import ElementTree as XML

DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
EPUB = 'application/epub+zip'
XLSX='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
PPTX='application/vnd.openxmlformats-officedocument.presentationml.presentation'
ODT='application/vnd.oasis.opendocument.text'
ODS='application/vnd.oasis.opendocument.spreadsheet'
ODP='application/vnd.oasis.opendocument.presentation'
OFFICE_TYPES=[XLSX,PPTX,ODT,ODS,ODP]
SUPPORTED = ['text/plain', 'text/markdown', 'text/html', DOCX, 'application/pdf', EPUB]+OFFICE_TYPES+['text/csv','text/tab-separated-values']


class FormatError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class Output:
    def __init__(self, limits):
        self.limits = limits
        self.blocks = []
        self.warnings = []
        self.candidates = []
        self.heading_path = []
        self.bytes = 0
        self.page_count = None
        self.parser = 'juanzhan-text'

    def warn(self, code):
        if code not in self.warnings:
            self.warnings.append(code)

    def candidate(self, key, value, source, locator=None):
        if isinstance(value,str) and value.strip():
            if len(self.candidates) >= 1000:
                raise FormatError('RESULT_LIMIT')
            self.candidates.append({'key':key,'value':value.strip(),'source':source,
                                    'confidence':None, **({'locator':locator} if locator else {})})

    def add(self, type, text, locator=None, **extra):
        if len(self.blocks) >= self.limits['max_blocks']:
            raise FormatError('RESULT_LIMIT')
        self.bytes += len(text.encode('utf-8'))
        if self.bytes > self.limits['max_output_bytes']:
            raise FormatError('RESULT_LIMIT')
        if type == 'heading':
            level = extra.get('level',1)
            self.heading_path = self.heading_path[:level-1] + [text]
        locator = locator or ({'kind':'section','heading_path':list(self.heading_path)} if self.heading_path else {'kind':'unknown'})
        self.blocks.append({'id':f'b{len(self.blocks)}','index':len(self.blocks),
                            'type':type,'text':text,'locator':locator,'confidence':None,**extra})

    def prose(self, text, locator=None):
        # Long runs are bounded fragments, not fabricated semantic paragraphs.
        if len(text)>4096:
            self.warn('TEXT_SEGMENT_SPLIT')
        for start in range(0,len(text),4096):
            location = locator
            if locator and locator['kind']=='character':
                location={**locator,'start':locator['start']+start,'end':min(locator['start']+start+4096,locator['end'])}
            self.add('unknown' if len(text)>4096 else 'paragraph',text[start:start+4096],location)


def decode(data):
    if data.startswith((b'\xff\xfe\0\0',b'\0\0\xfe\xff')):
        encoding='utf-32'
    elif data.startswith((b'\xff\xfe',b'\xfe\xff')):
        encoding='utf-16'
    else:
        encoding='utf-8-sig'
    try:
        text=data.decode(encoding)
    except UnicodeError:
        raise FormatError('INVALID_TEXT_ENCODING') from None
    if any(ord(c)<32 and c not in '\t\r\n\f' for c in text):
        raise FormatError('INVALID_TEXT_CONTENT')
    return text


def text_format(data,out):
    text=decode(data)
    out.parser='juanzhan-text'
    for match in re.finditer(r'.+?(?:\r?\n[ \t]*\r?\n|\Z)',text,re.S):
        out.prose(match[0],{'kind':'character','start':match.start(),'end':match.end()})


def inline_text(token):
    # Keep text/code/link labels; discard raw HTML and never serialize active href/src.
    parts=[]
    blocked=[]
    for child in token.children or []:
        if child.type=='html_inline':
            match=re.match(r'</?\s*([a-z0-9]+)',child.content,re.I)
            if match and match[1].lower() in ('script','style','iframe','object','svg','math','template'):
                if child.content.startswith('</'):
                    if blocked:blocked.pop()
                elif not child.content.rstrip().endswith('/>'):blocked.append(match[1].lower())
            continue
        if blocked:continue
        if child.type in ('text','code_inline'):
            parts.append(child.content)
        elif child.type in ('softbreak','hardbreak'):
            parts.append('\n')
        elif child.type=='image':
            parts.append(child.content)
    return ''.join(parts)


def markdown_format(data,out):
    from markdown_it import MarkdownIt
    text=decode(data)
    out.parser='markdown-it-py'
    tokens=MarkdownIt('commonmark',{'html':True,'maxNesting':64}).enable('table').parse(text)
    offsets=[0]
    for line in text.splitlines(keepends=True):offsets.append(offsets[-1]+len(line))
    list_depth=0
    heading=None
    table=None
    row=None
    cell=None
    for token in tokens:
        if token.type in ('bullet_list_open','ordered_list_open'):list_depth+=1
        elif token.type in ('bullet_list_close','ordered_list_close'):list_depth-=1
        elif token.type=='heading_open':heading=int(token.tag[1])
        elif token.type=='table_open':table=[]
        elif token.type=='tr_open':row=[]
        elif token.type in ('th_open','td_open'):cell=True
        elif token.type in ('th_close','td_close'):cell=None
        elif token.type=='tr_close':table.append(row)
        elif token.type=='table_close':
            rows=table
            out.add('table','\n'.join('\t'.join(r) for r in rows),table={'headers':rows[0] if rows else [],'rows':rows[1:]})
            table=None
        elif token.type=='inline':
            content=inline_text(token)
            if any(c.type in ('html_inline','image','link_open') for c in token.children or []):out.warn('ACTIVE_MARKUP_AND_RESOURCES_OMITTED')
            if cell:
                row.append(content)
                continue
            location={'kind':'character','start':offsets[token.map[0]],'end':offsets[token.map[1]]} if token.map else {'kind':'unknown'}
            if heading:
                out.add('heading',content,location,level=heading)
                heading=None
            elif list_depth:out.add('list_item',content,location)
            else:out.prose(content,location if len(content)<=4096 else {'kind':'unknown'})
        elif token.type in ('fence','code_block'):
            out.add('unknown',token.content,{'kind':'character','start':offsets[token.map[0]],'end':offsets[token.map[1]]})
            out.warn('CODE_BLOCK_AS_TEXT')
        elif token.type=='html_block':out.warn('ACTIVE_MARKUP_AND_RESOURCES_OMITTED')


class SafeZip:
    def __init__(self,data,limits):
        self.limit=limits['max_archive_bytes']
        self.read_bytes=0
        try:
            self.archive=zipfile.ZipFile(BytesIO(data))
            entries=self.archive.infolist()
            if len(entries)>limits['max_archive_entries'] or sum(e.file_size for e in entries)>self.limit:
                raise FormatError('ARCHIVE_LIMIT')
            self.entries={}
            for entry in entries:
                name=entry.filename
                parts=name.rstrip('/').split('/')
                if (not name or name.startswith('/') or '\\' in name or '\0' in name or
                    any(p in ('','.','..') for p in parts) or ':' in parts[0] or name in self.entries or
                    stat.S_ISLNK(entry.external_attr>>16) or entry.flag_bits&1 or
                    entry.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED)):
                    raise FormatError('UNSAFE_ARCHIVE')
                if entry.file_size>limits['max_archive_member_bytes'] or entry.file_size>max(1,entry.compress_size)*limits['max_compression_ratio']:
                    raise FormatError('ARCHIVE_LIMIT')
                self.entries[name]=entry
        except (zipfile.BadZipFile,ValueError):
            raise FormatError('INVALID_ARCHIVE') from None

    def read(self,name):
        if name not in self.entries or name.endswith('/'):
            raise FormatError('INVALID_PACKAGE')
        entry=self.entries[name]
        self.read_bytes+=entry.file_size
        if self.read_bytes>self.limit:raise FormatError('ARCHIVE_LIMIT')
        try:
            with self.archive.open(entry) as file:
                content=file.read(entry.file_size+1)
            if len(content)!=entry.file_size:raise FormatError('INVALID_ARCHIVE')
            return content
        except (zipfile.BadZipFile,RuntimeError,EOFError):
            raise FormatError('INVALID_ARCHIVE') from None

    def xml(self,name):
        try:
            return XML.fromstring(self.read(name),forbid_dtd=True,forbid_entities=True,forbid_external=True)
        except Exception as error:
            if isinstance(error,FormatError):raise
            raise FormatError('UNSAFE_OR_INVALID_XML') from None

    def __enter__(self):return self
    def __exit__(self,*_):self.archive.close()


def tag(element):return element.tag.rsplit('}',1)[-1]


def docx_format(data,out):
    out.parser='juanzhan-docx-xml'
    with SafeZip(data,out.limits) as package:
        root=package.xml('word/document.xml')
        body=next((e for e in root if tag(e)=='body'),None)
        if body is None:raise FormatError('INVALID_PACKAGE')
        w='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        styles={}
        if 'word/styles.xml' in package.entries:
            for style in package.xml('word/styles.xml'):
                styles[style.get(w+'styleId','')]=style
        def style_properties(id):
            heading=None
            numbered=None
            seen=set()
            while id in styles:
                if id in seen or len(seen)>=64:raise FormatError('INVALID_DOCX_STYLES')
                seen.add(id)
                current=styles[id]
                outline=current.find(w+'pPr/'+w+'outlineLvl')
                if heading is None and outline is not None and outline.get(w+'val','') in ('0','1','2','3','4','5'):
                    heading=int(outline.get(w+'val'))+1
                num=current.find(w+'pPr/'+w+'numPr/'+w+'numId')
                if numbered is None and num is not None:numbered=num.get(w+'val','0')!='0'
                parent=current.find(w+'basedOn')
                id=parent.get(w+'val') if parent is not None else None
            return heading,bool(numbered)
        def paragraph(element):
            parts=[]
            for item in element.iter():
                if tag(item)=='t':parts.append(item.text or '')
                elif tag(item)=='tab':parts.append('\t')
                elif tag(item) in ('br','cr'):parts.append('\n')
                elif tag(item) in ('drawing','pict'):out.warn('IMAGES_NOT_EXTRACTED')
                elif tag(item) in ('footnoteReference','endnoteReference'):out.warn('FOOTNOTES_NOT_EXTRACTED')
                elif tag(item) in ('ins','del'):out.warn('TRACKED_CHANGES_PRESENT')
            return ''.join(parts)
        for element in body:
            if tag(element)=='p':
                text=paragraph(element)
                style=element.find(w+'pPr/'+w+'pStyle')
                match=re.fullmatch(r'Heading([1-6])',style.get(w+'val',''),re.I) if style is not None else None
                inherited,list_style=style_properties(style.get(w+'val') if style is not None else None)
                num=element.find(w+'pPr/'+w+'numPr/'+w+'numId')
                numbered=num.get(w+'val','0')!='0' if num is not None else list_style
                outline=element.find(w+'pPr/'+w+'outlineLvl')
                explicit=int(outline.get(w+'val'))+1 if outline is not None and outline.get(w+'val','') in ('0','1','2','3','4','5') else None
                level=explicit or inherited or (int(match[1]) if match else None)
                if level:out.add('heading',text,level=level)
                elif numbered:out.add('list_item',text)
                elif text:out.prose(text)
            elif tag(element)=='tbl':
                rows=[]
                headers=[]
                for index,tr in enumerate(element.findall(w+'tr')):
                    values=['\n'.join(paragraph(p) for p in tc.iter(w+'p')) for tc in tr.findall(w+'tc')]
                    if any(tc.find(w+'tbl') is not None for tc in tr.findall(w+'tc')):out.warn('NESTED_TABLES_FLATTENED')
                    header=tr.find(w+'trPr/'+w+'tblHeader')
                    if index==0 and header is not None and header.get(w+'val','true').lower() not in ('0','false','off'):headers=values
                    else:rows.append(values)
                    if any(tag(e) in ('gridSpan','vMerge') for e in tr.iter()):out.warn('MERGED_CELLS_FLATTENED')
                out.add('table','\n'.join('\t'.join(r) for r in ([headers] if headers else [])+rows),table={'headers':headers,'rows':rows})
            elif tag(element)!='sectPr':out.warn('UNSUPPORTED_DOCX_BODY_ELEMENT')
        if 'docProps/core.xml' in package.entries:
            for item in package.xml('docProps/core.xml'):
                key={'title':'title','creator':'author','language':'language'}.get(tag(item))
                if key:out.candidate(key,item.text,'document_properties')
        if any(name.startswith(('word/header','word/footer')) for name in package.entries):out.warn('HEADERS_FOOTERS_OMITTED')
        out.warn('DOCX_LAYOUT_NOT_PRESERVED')


def safe_href(base,href):
    uri=urlsplit(href)
    path=unquote(uri.path)
    if uri.scheme or uri.netloc or uri.query or not path or path.startswith('/') or '\\' in path or '\0' in path:
        raise FormatError('UNSAFE_PACKAGE_REFERENCE')
    result=posixpath.normpath(posixpath.join(posixpath.dirname(base),path))
    if result=='..' or result.startswith('../') or result.startswith('/'):
        raise FormatError('UNSAFE_PACKAGE_REFERENCE')
    return result


def epub_format(data,out):
    from .conversion_html import html_format
    out.parser='juanzhan-epub-spine'
    with SafeZip(data,out.limits) as package:
        if package.read('mimetype')!=b'application/epub+zip':raise FormatError('INVALID_PACKAGE')
        container=package.xml('META-INF/container.xml')
        roots=[item for item in container.iter() if tag(item)=='rootfile']
        if not roots:raise FormatError('INVALID_PACKAGE')
        path=safe_href('',roots[0].get('full-path',''))
        root=package.xml(path)
        manifest=next((e for e in root if tag(e)=='manifest'),None)
        spine=next((e for e in root if tag(e)=='spine'),None)
        if manifest is None or spine is None:raise FormatError('INVALID_PACKAGE')
        items={}
        for item in manifest:
            id=item.get('id')
            if not id or id in items:raise FormatError('INVALID_PACKAGE')
            items[id]=item
        for element in root:
            if tag(element)=='metadata':
                for item in element:
                    key={'title':'title','creator':'author','language':'language'}.get(tag(item))
                    if key:out.candidate(key,item.text,'epub_manifest')
        if len(spine)>out.limits['max_archive_entries']:raise FormatError('ARCHIVE_LIMIT')
        for index,item in enumerate(spine):
            entry=items.get(item.get('idref'))
            if entry is None:raise FormatError('INVALID_PACKAGE')
            href=safe_href(path,entry.get('href',''))
            if entry.get('media-type') not in ('application/xhtml+xml','text/html'):
                out.warn('NON_HTML_SPINE_ITEM_OMITTED')
                continue
            # XHTML goes through hardened XML validation before text extraction.
            content=package.read(href)
            if entry.get('media-type')=='application/xhtml+xml':
                try:
                    chapter=XML.fromstring(content,forbid_dtd=True,forbid_entities=True,forbid_external=True)
                    for element in chapter.iter():
                        element.tag=tag(element)
                        element.attrib={key.rsplit('}',1)[-1]:value for key,value in element.attrib.items()}
                    from xml.etree.ElementTree import tostring
                    content=tostring(chapter,encoding='utf-8',method='html')
                except Exception:raise FormatError('UNSAFE_OR_INVALID_XML') from None
            before=len(out.blocks)
            out.heading_path=[]
            html_format(content,out,collect_metadata=False)
            for block in out.blocks[before:]:
                heading=block['locator'].get('heading_path')
                block['locator']={'kind':'epub','spine_index':index,'href':href,**({'heading_path':heading} if heading else {})}
        out.parser='juanzhan-epub-spine'
        out.warn('EPUB_REFLOW_NO_PHYSICAL_PAGES')


def pdf_format(data,out, missing_page=None):
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError, DependencyError
    out.parser='pypdf'
    try:
        reader=PdfReader(BytesIO(data),strict=True)
        if reader.is_encrypted:raise FormatError('PDF_PASSWORD_REQUIRED')
        count=len(reader.pages)
        if count>out.limits['max_pages']:raise FormatError('PAGE_LIMIT')
        out.page_count=count or None
        for index,page in enumerate(reader.pages):
            content=page.get_contents()
            if content is not None and len(content.get_data())>out.limits['max_archive_member_bytes']:raise FormatError('PDF_STREAM_LIMIT')
            text=page.extract_text() or ''
            if index:out.add('page_break','',{'kind':'page','page':index+1})
            if text.strip():out.prose(text,{'kind':'page','page':index+1})
            elif missing_page is not None:missing_page(index)
            else:out.warn('NO_TEXT_LAYER_OCR_REQUIRED')
        if reader.metadata:
            for prop,key in (('/Title','title'),('/Author','author')):
                out.candidate(key,reader.metadata.get(prop),'document_properties')
        out.warn('PDF_READING_ORDER_AND_TABLES_UNVERIFIED')
    except FormatError:raise
    except DependencyError:raise FormatError('PDF_ENCRYPTION_UNSUPPORTED') from None
    except (PdfReadError,ValueError,KeyError,TypeError,RecursionError):
        raise FormatError('INVALID_PDF') from None


def escaped(text):
    text=html.escape(text,quote=False)
    return re.sub(r'([\\`*_{}\[\]()#+.!|>\-])',r'\\\1',text)


def markdown_artifact(blocks):
    parts=[]
    for block in blocks:
        value=escaped(block['text'])
        if block['type']=='heading':value='#'*block['level']+' '+value
        elif block['type']=='list_item':value='- '+value
        elif block['type']=='table':
            table=block['table']
            # Keep unlabelled rows unlabelled rather than inventing a header.
            rows=([table['headers']] if table['headers'] else [])+table['rows']
            if table['headers'] and all(len(row)==len(table['headers']) and all('\n' not in cell for cell in row) for row in rows):
                lines=['| '+' | '.join(escaped(cell) for cell in row)+' |' for row in rows]
                lines.insert(1,'| '+' | '.join('---' for _ in table['headers'])+' |')
                value='\n'.join(lines)
            else:value='\n'.join(' | '.join(escaped(cell) for cell in row) for row in rows)
        parts.append(value)
    return '\n\n'.join(parts)
