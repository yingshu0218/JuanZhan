"""Text-only HTML extraction. No browser, network, CSS, script or source HTML output."""
from html.parser import HTMLParser
import re
from .conversion_formats import FormatError, decode

VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
ACTIVE={'script','style','iframe','object','embed','svg','math','template','noscript','select','textarea','button'}
BOUNDARY={'p','div','article','section','header','footer','main','aside','blockquote','pre','li'}


class TextHTML(HTMLParser):
    def __init__(self,out,collect_metadata):
        super().__init__(convert_charrefs=True)
        self.out=out
        self.collect_metadata=collect_metadata
        self.stack=[]
        self.buffer=[]
        self.heading=None
        self.list_depth=0
        self.table=None
        self.row=None
        self.cell=None
        self.cell_header=False
        self.row_headers=[]
        self.title=[]

    def blocked(self):return any(hidden for _,hidden in self.stack)

    def flush(self):
        text=re.sub(r'\s+',' ',''.join(self.buffer)).strip()
        self.buffer=[]
        if text:
            if self.heading:self.out.add('heading',text,level=self.heading)
            elif self.list_depth:self.out.add('list_item',text)
            else:self.out.prose(text)

    def handle_starttag(self,name,attrs):
        attributes=dict(attrs)
        hidden=(name in ACTIVE or 'hidden' in attributes or attributes.get('aria-hidden')=='true' or
                bool(re.search(r'(?:display\s*:\s*none|visibility\s*:\s*hidden)',attributes.get('style') or '',re.I)))
        if len(self.stack)>=64:raise FormatError('HTML_DEPTH_LIMIT')
        if name in ACTIVE or name in ('img','link','base') or any(key.lower().startswith('on') for key in attributes):
            self.out.warn('ACTIVE_MARKUP_AND_RESOURCES_OMITTED')
        if not self.blocked() and not hidden:
            if self.collect_metadata:
                if name=='html':self.out.candidate('language',attributes.get('lang'),'html_meta')
                if name=='meta':
                    key={'author':'author','description':'description','keywords':'keywords','language':'language'}.get((attributes.get('name') or '').lower())
                    if key:self.out.candidate(key,attributes.get('content'),'html_meta')
            if name=='title':self.title=[]
            if name in BOUNDARY or re.fullmatch('h[1-6]',name):self.flush()
            if re.fullmatch('h[1-6]',name):self.heading=int(name[1])
            if name in ('ul','ol'):self.list_depth+=1
            if name=='br':self.handle_data(' ')
            if name=='img' and attributes.get('alt'):self.handle_data(attributes['alt'])
            if name=='table':
                self.flush()
                if self.table is not None:raise FormatError('HTML_NESTED_TABLE_UNSUPPORTED')
                self.table=[]
            elif name=='tr' and self.table is not None:self.row=[];self.row_headers=[]
            elif name in ('td','th') and self.row is not None:
                self.cell=[];self.cell_header=name=='th'
                if any(attributes.get(key,'1')!='1' for key in ('colspan','rowspan')):self.out.warn('MERGED_CELLS_FLATTENED')
        if name not in VOID:self.stack.append((name,hidden))

    def handle_startendtag(self,name,attrs):
        self.handle_starttag(name,attrs)
        if name not in VOID:self.handle_endtag(name)

    def handle_endtag(self,name):
        blocked=self.blocked()
        if not blocked:
            if name in ('td','th') and self.cell is not None:
                self.row.append(re.sub(r'\s+',' ',''.join(self.cell)).strip())
                self.row_headers.append(self.cell_header)
                self.cell=None
            elif name=='tr' and self.table is not None and self.row is not None:
                self.table.append((self.row,all(self.row_headers) and bool(self.row_headers)))
                self.row=None
            elif name=='table' and self.table is not None:
                headers=self.table[0][0] if self.table and self.table[0][1] else []
                rows=[row for row,_ in self.table[(1 if headers else 0):]]
                self.out.add('table','\n'.join('\t'.join(row) for row in ([headers] if headers else [])+rows),table={'headers':headers,'rows':rows})
                self.table=None
            elif name=='title' and self.collect_metadata:
                self.out.candidate('title',''.join(self.title),'html_meta')
            elif name in BOUNDARY or re.fullmatch('h[1-6]',name):self.flush()
            if re.fullmatch('h[1-6]',name):self.heading=None
            if name in ('ul','ol'):self.list_depth=max(0,self.list_depth-1)
        for index in range(len(self.stack)-1,-1,-1):
            if self.stack[index][0]==name:
                if index!=len(self.stack)-1:self.out.warn('MALFORMED_HTML_RECOVERED')
                self.stack=self.stack[:index]
                break

    def handle_data(self,value):
        if self.blocked():return
        if any(tag=='title' for tag,_ in self.stack):self.title.append(value);return
        if any(tag=='head' for tag,_ in self.stack):return
        if self.cell is not None:self.cell.append(value)
        else:self.buffer.append(value)


def html_format(data,out,collect_metadata=True):
    out.parser='juanzhan-html-text'
    parser=TextHTML(out,collect_metadata)
    parser.feed(decode(data))
    parser.close()
    parser.flush()
    if parser.table is not None:out.warn('INCOMPLETE_HTML_TABLE_OMITTED')
    out.warn('HTML_LAYOUT_AND_CSS_NOT_PRESERVED')
