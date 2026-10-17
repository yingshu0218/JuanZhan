"""Versioned retrieval tokens, not semantic word segmentation or language inference."""
from functools import lru_cache
import hashlib
from importlib.metadata import version
from pathlib import Path
import unicodedata

import regex

DICTIONARY_SHA256='4ffd2aa3019bda697f811e0d7e27604e30c9f30b31204af1b89622f7cd818179'
VERSION='han12-v1-nfkc'+unicodedata.unidata_version+'-opencc017-'+DICTIONARY_SHA256[:16]+'-regex'+version('regex')
RUNS=regex.compile(r'\p{Han}+|(?:(?!\p{Han})[\p{L}\p{N}])+')
HAN=regex.compile(r'\p{Han}')
MAX_TOKENS=500000
MAX_OUTPUT=16*1024*1024

class TokenLimit(ValueError):pass

@lru_cache(maxsize=1)
def converter():
    import opencc
    if version('opencc-python-reimplemented')!='0.1.7':raise TokenLimit('TOKENIZER_VERSION_MISMATCH')
    root=Path(opencc.__file__).parent;digest=hashlib.sha256()
    for path in sorted(p for p in root.rglob('*') if p.is_file() and p.suffix in ('.txt','.json')):
        digest.update(str(path.relative_to(root)).encode()+b'\0'+path.read_bytes()+b'\0')
    if digest.hexdigest()!=DICTIONARY_SHA256:raise TokenLimit('TOKENIZER_DICTIONARY_MISMATCH')
    return opencc.OpenCC('t2s')


def tokens(text):
    text=converter().convert(unicodedata.normalize('NFKC',text).casefold())
    for match in RUNS.finditer(text):
        run=match.group()
        if HAN.fullmatch(run[0]):
            for i,char in enumerate(run):
                yield char
                if i+1<len(run):yield run[i:i+2]
        else:
            for i in range(0,len(run),128):yield run[i:i+128]


def indexed(texts):
    output=[];size=0
    for text in texts:
        for token in tokens(text):
            size+=len(token.encode())+1
            if len(output)>=MAX_TOKENS or size>MAX_OUTPUT:raise TokenLimit('INDEX_TOKEN_LIMIT')
            output.append(token)
    return ' '.join(output)


def match_expression(query):
    if not isinstance(query,str) or not 1<=len(query)<=512:raise ValueError('Invalid query length')
    values=list(tokens(query))
    if not values or len(values)>256:raise ValueError('Invalid query token count')
    return ' AND '.join('"'+v.replace('"','""')+'"' for v in dict.fromkeys(values))
