"""Bounded stateless MCP tools over JSON Streamable HTTP, with legacy handshakes."""
import base64
import json
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from .agent_api import INSTRUCTIONS, TOOLS, call, json_body, tools
from .auth import fail

MODERN='2026-07-28'
LEGACY=('2025-11-25','2025-06-18')
VERSIONS=(MODERN,*LEGACY)
HEADERS={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
INFO={'name':'juanzhan','version':'1.0.0'}

def error(id,code,message,status=200,data=None):
    value={'code':code,'message':message}
    if data is not None:value['data']=data
    return JSONResponse({'jsonrpc':'2.0','id':id,'error':value},status_code=status,headers=HEADERS)

def decoded(value):
    if value and value.startswith('=?base64?') and value.endswith('?='):
        try:return base64.b64decode(value[9:-2],validate=True).decode('utf-8')
        except (ValueError,UnicodeError):return None
    return value

def router(settings):
    routes=APIRouter(prefix='/api/v1/agent')
    @routes.post('/mcp')
    async def mcp(request: Request):
        if request.state.auth_mode!='agent':fail(403,'AGENT_TOKEN_REQUIRED','Use a scoped agent credential for MCP')
        origin=request.headers.get('origin')
        if origin is not None and origin!=str(request.base_url).rstrip('/'):
            fail(403,'ORIGIN_REJECTED','Origin does not match this server')
        accept={part.split(';')[0].strip().lower() for part in request.headers.get('accept','').split(',')}
        if 'application/json' not in accept or 'text/event-stream' not in accept:
            return error(None,-32600,'Accept must include application/json and text/event-stream',406)
        try:body=await json_body(request)
        except HTTPException as exc:return error(None,-32700,'Invalid JSON request',exc.status_code)
        if not isinstance(body,dict) or body.get('jsonrpc')!='2.0' or not isinstance(body.get('method'),str):
            return error(None,-32600,'Expected a single JSON-RPC request',400)
        id=body.get('id');method=body['method'];params=body.get('params',{})
        if ('id' in body and (id is None or isinstance(id,bool) or not isinstance(id,(str,int)))) or not isinstance(params,dict):
            return error(None,-32600,'Invalid request ID or parameters',400)
        header=request.headers.get('mcp-protocol-version')
        meta=params.get('_meta',{})
        if not isinstance(meta,dict):return error(id,-32602,'Invalid request metadata',400)
        modern=header==MODERN or meta.get('io.modelcontextprotocol/protocolVersion')==MODERN
        version=header
        if method=='initialize' and not modern:
            version=params.get('protocolVersion')
            if version not in LEGACY:version=LEGACY[0]
        elif version not in VERSIONS:
            return error(id,-32022,'Unsupported protocol version',400,{'supported':list(VERSIONS),'requested':version})
        if modern:
            info=meta.get('io.modelcontextprotocol/clientInfo')
            capabilities=meta.get('io.modelcontextprotocol/clientCapabilities')
            if header!=MODERN or meta.get('io.modelcontextprotocol/protocolVersion')!=header or request.headers.get('mcp-method')!=method:
                return error(id,-32020,'Header mismatch',400)
            if method=='tools/call' and decoded(request.headers.get('mcp-name'))!=params.get('name'):
                return error(id,-32020,'Header mismatch',400)
            if not isinstance(info,dict) or not all(isinstance(info.get(key),str) and 1<=len(info[key])<=128 for key in ('name','version')) or not isinstance(capabilities,dict):
                return error(id,-32602,'Required client metadata missing',400)
        if 'id' not in body:
            if not modern and method in ('notifications/initialized','notifications/cancelled'):
                return Response(status_code=202,headers=HEADERS)
            return error(None,-32600,'Unsupported notification',400)
        result=None
        if method=='initialize' and not modern:
            if not isinstance(params.get('capabilities'),dict) or not isinstance(params.get('clientInfo'),dict):
                return error(id,-32602,'Client capabilities and identity required')
            result={'protocolVersion':version,'serverInfo':INFO,'capabilities':{'tools':{}},'instructions':INSTRUCTIONS}
        elif method=='server/discover' and modern:
            result={'resultType':'complete','supportedVersions':list(VERSIONS),'capabilities':{'tools':{}},
                    '_meta':{'io.modelcontextprotocol/serverInfo':INFO},'instructions':INSTRUCTIONS}
        elif method=='ping':result={}
        elif method=='tools/list':
            if params.get('cursor') is not None:return error(id,-32602,'Unknown pagination cursor')
            result={'tools':tools()}
        elif method=='tools/call':
            name=params.get('name');arguments=params.get('arguments',{})
            if not isinstance(name,str) or not isinstance(arguments,dict):return error(id,-32602,'Invalid tool call')
            if name not in TOOLS:return error(id,-32602,'Unknown read-only tool')
            try:
                value=await run_in_threadpool(call,settings,request,name,arguments)
                result={'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False)}],'structuredContent':value,'isError':False}
            except HTTPException as exc:
                detail=exc.detail if isinstance(exc.detail,dict) else {'code':'REQUEST_REJECTED'}
                result={'content':[{'type':'text','text':json.dumps({'error':{'code':detail['code'],'message':detail.get('message','Request rejected')}})}],'isError':True}
        else:return error(id,-32601,'Method not found',404 if modern else 200)
        if modern:result['resultType']='complete'
        return JSONResponse({'jsonrpc':'2.0','id':id,'result':result},headers=HEADERS)
    return routes
