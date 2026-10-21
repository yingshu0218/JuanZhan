"""Bounded MS-PPT current-persist-directory text extraction; never scan obsolete edits."""
from io import BytesIO
import re
import struct
import olefile
from .conversion_formats import FormatError

class Records:
    def __init__(self,data):self.data=data;self.count=0
    def header(self,offset,end=None):
        end=len(self.data) if end is None else end
        if offset<0 or offset+8>end:raise FormatError('INVALID_PPT_RECORD')
        flags,kind,size=struct.unpack_from('<HHI',self.data,offset)
        stop=offset+8+size
        if stop>end:raise FormatError('INVALID_PPT_RECORD')
        return flags&15,flags>>4,kind,offset+8,stop
    def children(self,start,end):
        while start<end:
            self.count+=1
            if self.count>100000:raise FormatError('PPT_RECORD_LIMIT')
            record=self.header(start,end);yield record;start=record[4]
    def uint(self,position,end):
        if position+4>end:raise FormatError('INVALID_PPT_RECORD')
        return struct.unpack_from('<I',self.data,position)[0]
    def text(self,record):
        _,_,kind,start,end=record
        try:
            value=self.data[start:end].decode('utf-16-le' if kind==4000 else 'cp1252')
        except UnicodeError:raise FormatError('INVALID_PPT_TEXT') from None
        value=value.replace('\r','\n').replace('\x0b','\n').replace('\f','\n\n')
        return re.sub(r'[\x00-\x08\x0e-\x1f]','',value).strip()

def ppt_format(data,out):
    out.parser='juanzhan-ppt-persist'
    with olefile.OleFileIO(BytesIO(data)) as package:
        if package.exists('EncryptedSummary'):raise FormatError('OFFICE_PASSWORD_REQUIRED')
        if not package.exists('Current User') or not package.exists('PowerPoint Document'):raise FormatError('INVALID_PPT_PACKAGE')
        user=package.openstream('Current User').read(20)
        if len(user)!=20:raise FormatError('INVALID_PPT_PACKAGE')
        token=int.from_bytes(user[12:16],'little')
        if token==0xf3d1c4df:raise FormatError('OFFICE_PASSWORD_REQUIRED')
        if token!=0xe391c05f:raise FormatError('INVALID_PPT_PACKAGE')
        stream=package.openstream('PowerPoint Document').read(out.limits['max_archive_member_bytes']+1)
        if len(stream)>out.limits['max_archive_member_bytes']:raise FormatError('ARCHIVE_LIMIT')
    reader=Records(stream);offset=int.from_bytes(user[16:20],'little');seen=set();directory={};document=None
    while offset:
        if offset in seen or len(seen)>=256:raise FormatError('INVALID_PPT_EDIT_CHAIN')
        seen.add(offset);_,_,kind,start,end=reader.header(offset)
        if kind!=4085 or end-start not in (28,32):raise FormatError('INVALID_PPT_EDIT_CHAIN')
        if end-start==32 and reader.uint(start+28,end):raise FormatError('OFFICE_PASSWORD_REQUIRED')
        previous=reader.uint(start+8,end);persist=reader.uint(start+12,end)
        if previous>=offset or not previous<persist<offset:raise FormatError('INVALID_PPT_EDIT_CHAIN')
        if document is None:document=reader.uint(start+16,end)
        _,_,kind,pstart,pend=reader.header(persist)
        if kind not in (6001,6002):raise FormatError('INVALID_PPT_DIRECTORY')
        while pstart<pend:
            entry=reader.uint(pstart,pend);pstart+=4
            first=entry&0xfffff;count=entry>>20
            if not first or not count or first+count>0x100000 or len(directory)+count>100000:raise FormatError('PPT_RECORD_LIMIT')
            for index in range(count):
                target=reader.uint(pstart,pend);pstart+=4
                if target+8>len(stream):raise FormatError('INVALID_PPT_DIRECTORY')
                directory.setdefault(first+index,target)
        offset=previous
    def object_record(id,expected):
        if id not in directory:raise FormatError('INVALID_PPT_REFERENCE')
        record=reader.header(directory[id])
        if record[0]!=15 or record[2]!=expected:raise FormatError('INVALID_PPT_REFERENCE')
        return record
    root=object_record(document,1000)
    lists=[r for r in reader.children(root[3],root[4]) if r[2]==4080 and r[1] in (0,2)]
    lists.sort(key=lambda record:record[1])
    def shape_text(record,outline,depth=0):
        if depth>64:raise FormatError('PPT_RECORD_LIMIT')
        texts=[]
        for child in reader.children(record[3],record[4]):
            if child[2]==0xf00d:
                values=[];refs=[]
                for part in reader.children(child[3],child[4]):
                    if part[2] in (4000,4008):values.append(reader.text(part))
                    elif part[2]==3998:refs.append(reader.uint(part[3],part[4]))
                if any(values):texts.extend(values)
                else:
                    for ref in refs:
                        if ref>=len(outline):raise FormatError('INVALID_PPT_TEXT_REFERENCE')
                        texts.append(outline[ref])
            elif child[0]==15:texts.extend(shape_text(child,outline,depth+1))
        return texts
    for collection in lists:
        groups=[];group=None
        for item in reader.children(collection[3],collection[4]):
            if item[2]==1011:
                group=[reader.uint(item[3],item[4]),[]];groups.append(group)
            elif group is not None and item[2]==3999:group[1].append('')
            elif group is not None and item[2] in (4000,4008):
                if not group[1]:raise FormatError('INVALID_PPT_TEXT_REFERENCE')
                group[1][-1]+=reader.text(item)
        if len(groups)>out.limits['max_pages']:raise FormatError('PAGE_LIMIT')
        notes=collection[1]==2
        for index,(id,outline) in enumerate(groups):
            record=object_record(id,1008 if notes else 1006)
            texts=shape_text(record,outline)
            if not texts:
                texts=outline
                if any(texts):out.warn('PPT_OUTLINE_TEXT_FALLBACK')
            texts=[text for text in texts if text.strip()]
            if not texts:continue
            label=('备注 ' if notes else '幻灯片 ')+str(index+1)
            location={'kind':'section','heading_path':[label]}
            out.add('heading',label,location,level=1)
            for text in texts:out.prose(text,location)
            if notes:out.warn('PPT_SPEAKER_NOTES_INCLUDED')
    out.warn('SLIDE_SHAPE_ORDER_NOT_VISUAL_READING_ORDER')
    out.warn('SLIDE_MASTER_CHARTS_IMAGES_AND_MEDIA_OMITTED')
    out.warn('MACROS_EMBEDDED_OBJECTS_AND_LINKS_NOT_EXECUTED')
