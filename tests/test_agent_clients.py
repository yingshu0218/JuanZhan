"""Actual TCP REST, MCP and stdio clients sharing a scoped token and persisted evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import Request,urlopen
from test_parsing import pipeline
from test_agents import credential,parsed
from test_converter import real_server


def test_real_tcp_rest_legacy_modern_mcp_and_stdio_bridge(pipeline):
    settings,client,_,space=pipeline;id=parsed(pipeline);token,headers=credential(pipeline)
    with real_server(client.app) as base:
        def send(path,body):
            req=Request(base+path,data=json.dumps(body).encode(),headers={**headers,'Content-Type':'application/json'},method='POST')
            with urlopen(req,timeout=10) as response:return json.load(response)
        result=send('/api/v1/agent/search',{'space_id':space,'text':'合同'})
        assert result['items'][0]['id']==id
        question='帮我找出合同金额及延期风险，并列出依据。'
        context=send('/api/v1/agent/analysis-context',{'space_id':space,'document_ids':[id],'question':question})
        assert context['question']==question and context['answer_generated'] is False
        assert '30000' in str(context) and '延期' in str(context)
        env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/'services'),JUANZHAN_MCP_URL=base+'/api/v1/agent/mcp',JUANZHAN_AGENT_TOKEN=token['token'])
        messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'stdio-agent','version':'1'}}},
                  {'jsonrpc':'2.0','method':'notifications/initialized'},
                  {'jsonrpc':'2.0','id':2,'method':'tools/list'},
                  {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'get_document_overview','arguments':{'space_id':space,'document_id':id}}}]
        process=subprocess.run([sys.executable,'-m','juanzhan.agent_stdio'],input=''.join(json.dumps(message)+'\n' for message in messages),capture_output=True,text=True,env=env,timeout=20)
        assert process.returncode==0,process.stderr
        responses=[json.loads(line) for line in process.stdout.splitlines()]
        assert len(responses)==3 and 'protocolVersion' in responses[0]['result']
        assert responses[2]['result']['structuredContent']['document_id']==id
        assert token['token'] not in process.stdout+process.stderr
        modern={'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'read_document','arguments':{'space_id':space,'document_id':id},'_meta':{
            'io.modelcontextprotocol/protocolVersion':'2026-07-28','io.modelcontextprotocol/clientInfo':{'name':'http-agent','version':'1'},'io.modelcontextprotocol/clientCapabilities':{}}}}
        req=Request(base+'/api/v1/agent/mcp',data=json.dumps(modern).encode(),headers={**headers,'Content-Type':'application/json','Accept':'application/json, text/event-stream',
            'MCP-Protocol-Version':'2026-07-28','Mcp-Method':'tools/call','Mcp-Name':'read_document'},method='POST')
        with urlopen(req,timeout=10) as response:
            value=json.load(response)['result'];assert value['resultType']=='complete' and value['structuredContent']['blocks']
