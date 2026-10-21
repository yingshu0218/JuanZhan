"""Dependency-free, vendor-neutral read-only REST client and JSON command line."""
import json
import os
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler, HTTPSHandler

class ClientError(Exception):
    pass

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

class Client:
    def __init__(self, base, token, *, ca_file=None):
        try:
            parsed=urlsplit(base);parsed.port
            valid=(parsed.scheme in ('http','https') and parsed.hostname and not parsed.username and not parsed.password
                and not parsed.query and not parsed.fragment and parsed.path.rstrip('/')=='/api/v1/agent'
                and not any(ord(c)<33 or ord(c)>126 for c in base) and '\\' not in base
                and (parsed.scheme=='https' or parsed.hostname in ('127.0.0.1','localhost','::1'))
                and token.startswith('jza_') and len(token)<=256 and all(c.isascii() and (c.isalnum() or c in '_-') for c in token))
            if not valid:raise ValueError()
            self.opener=build_opener(ProxyHandler({}),NoRedirect(),HTTPSHandler(context=ssl.create_default_context(cafile=ca_file)))
        except (ValueError,OSError):raise ClientError('Invalid private endpoint, credential or CA configuration') from None
        self.base=base.rstrip('/');self.token=token

    def call(self, name, arguments=None):
        values=dict(arguments or {});method='GET'
        if name=='list_spaces':path='/spaces';allowed=set()
        elif name=='get_formats':path='/capabilities';allowed=set()
        elif name=='get_catalog':path='/catalog';allowed={'space_id'}
        elif name in ('get_document_overview','read_document'):
            id=values.pop('document_id',None)
            if not isinstance(id,str) or not 1<=len(id)<=255:raise ClientError('A document ID is required')
            path='/documents/'+quote(id,safe='')+('/overview' if name=='get_document_overview' else '/content')
            allowed={'space_id'} if name=='get_document_overview' else {'space_id','parse_run_id','page','page_size'}
        elif name in ('search_documents','prepare_analysis'):
            path='/search' if name=='search_documents' else '/analysis-context';method='POST';allowed=None
        else:raise ClientError('Unknown read-only operation')
        if allowed is not None and set(values)-allowed:raise ClientError('Unknown operation parameter')
        try:
            data=json.dumps(values,ensure_ascii=False,allow_nan=False).encode() if method=='POST' else None
            if data and len(data)>65536:raise ValueError()
            if method=='GET' and values:path+='?'+urlencode({k:v for k,v in values.items() if v is not None})
            request=Request(self.base+path,data=data,method=method,headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json','Accept':'application/json'})
            with self.opener.open(request,timeout=30) as response:
                data=response.read(512*1024+1)
                if len(data)>512*1024:raise ValueError()
                return json.loads(data)
        except HTTPError as exc:
            raise ClientError('Document API rejected request (HTTP '+str(exc.code)+')') from None
        except (ValueError,UnicodeError,URLError,OSError):
            raise ClientError('Document API request failed') from None

def main():
    try:
        if len(sys.argv)!=2:raise ClientError('Pass one read-only operation; supply JSON arguments on stdin')
        data=sys.stdin.buffer.read(65537)
        if len(data)>65536:raise ClientError('Arguments exceed 64 KiB')
        values=json.loads(data or b'{}')
        if not isinstance(values,dict):raise ClientError('Arguments must be a JSON object')
        client=Client(os.environ.get('JUANZHAN_AGENT_URL','http://127.0.0.1:18080/api/v1/agent'),os.environ.get('JUANZHAN_AGENT_TOKEN',''),ca_file=os.environ.get('JUANZHAN_CA_FILE'))
        print(json.dumps(client.call(sys.argv[1],values),ensure_ascii=False));return 0
    except (ClientError,ValueError,TypeError):
        print('REST client request failed; check private configuration and JSON arguments.',file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
