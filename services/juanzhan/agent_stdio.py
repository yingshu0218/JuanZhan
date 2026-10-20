"""MCP stdio bridge for clients without custom HTTP headers; no extra packages."""
import json
import os
import sys
from urllib.error import HTTPError,URLError
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler

LIMIT=65536
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def main():
    endpoint=os.environ.get('JUANZHAN_MCP_URL','http://127.0.0.1:18080/api/v1/agent/mcp')
    token=os.environ.get('JUANZHAN_AGENT_TOKEN','')
    parsed=urlsplit(endpoint)
    if not token.startswith('jza_') or len(token)>256 or parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        print('Set a valid private JUANZHAN_AGENT_TOKEN and JUANZHAN_MCP_URL.',file=sys.stderr);return 2
    if parsed.scheme=='http' and parsed.hostname not in ('127.0.0.1','localhost','::1'):
        print('Use HTTPS outside loopback.',file=sys.stderr);return 2
    opener=build_opener(ProxyHandler({}),NoRedirect())
    version='2025-11-25'
    while True:
        line=sys.stdin.buffer.readline(LIMIT+1)
        if not line:return 0
        id=None
        try:
            if len(line)>LIMIT or not line.endswith(b'\n'):raise ValueError()
            body=json.loads(line);id=body.get('id')
            if not isinstance(body,dict):raise ValueError()
            params=body.get('params',{})
            meta=params.get('_meta',{}) if isinstance(params,dict) else {}
            current=meta.get('io.modelcontextprotocol/protocolVersion',version)
            headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'application/json, text/event-stream'}
            if body.get('method')!='initialize':headers['MCP-Protocol-Version']=current
            if current=='2026-07-28':
                headers['Mcp-Method']=body['method']
                if body['method']=='tools/call':headers['Mcp-Name']=params.get('name','')
            request=Request(endpoint,data=json.dumps(body,ensure_ascii=False).encode(),headers=headers,method='POST')
            try:
                with opener.open(request,timeout=30) as response:
                    data=response.read(2*1024*1024+1)
                    if response.status==202:continue
            except HTTPError as exc:
                data=exc.read(2*1024*1024+1)
                # Auth errors are transport failures, never expose credential values or HTTP traces.
                if exc.code in (401,403,429):raise ValueError() from None
            if len(data)>2*1024*1024:raise ValueError()
            value=json.loads(data)
            if body.get('method')=='initialize' and isinstance(value.get('result'),dict):
                version=value['result'].get('protocolVersion',version)
            if 'id' in body:print(json.dumps(value,ensure_ascii=False),flush=True)
        except (ValueError,UnicodeError,URLError,OSError,AttributeError,TypeError,KeyError):
            print(json.dumps({'jsonrpc':'2.0','id':id,'error':{'code':-32603,'message':'MCP bridge request failed; check private endpoint and credentials'}}),flush=True)
            if len(line)>LIMIT:return 2

if __name__=='__main__':raise SystemExit(main())
