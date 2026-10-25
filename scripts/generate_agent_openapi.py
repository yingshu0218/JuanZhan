"""Generate the explicit agent extension contract; no app or database is started."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services'))
from juanzhan.agent_access import TokenInput
from juanzhan.agent_imports import Submission
from juanzhan.agent_api import AgentSearch,AnalysisInput,MarkdownInput

S={'type':'string'};B={'type':'boolean'};I={'type':'integer'}
def array(item):return {'type':'array','items':item}
def obj(properties,required=None):return {'type':'object','properties':properties,'required':required or list(properties),'additionalProperties':False}
def ref(name):return {'$ref':'#/components/schemas/'+name}
nullable=lambda value:{'anyOf':[value,{'type':'null'}]}
schemas={}
for model in (TokenInput,AgentSearch,AnalysisInput,MarkdownInput,Submission):
    schema=model.model_json_schema(ref_template='#/components/schemas/{model}')
    schemas.update(schema.pop('$defs',{}));schemas[model.__name__]=schema
schemas['Error']=obj({'error':obj({'code':S,'message':S})})
schemas['AgentToken']=obj({'id':S,'name':S,'import_enabled':B,'space_ids':array(S),'created_at':S,'expires_at':S})
schemas['IssuedAgentToken']={'allOf':[{'type':'object','properties':{**schemas['AgentToken']['properties'],'token':S},'required':[*schemas['AgentToken']['required'],'token'],'additionalProperties':False}]}
schemas['Citation']=obj({'index':I,'block_id':nullable(S),'text':S,'locator':{'type':'object'}})
schemas['OverviewPoint']=obj({'label':S,'details':array(S),'index':I,'sources':array(ref('Citation'))})
schemas['Overview']=obj({'document_id':S,'document_version':I,'current_revision_id':nullable(S),'content_revision_id':nullable(S),'parse_run_id':nullable(S),
    'processing_status':S,'availability_status':S,'warnings':array(S),'text_available':B,'ocr_used':B,'stale_for_current_revision':B,
    'title':S,'method':{'const':'extractive-v2'},'points':array(ref('OverviewPoint')),'omitted':B,'partial':B,'covered':I,'total':I})
schemas['AgentBlock']=obj({'id':S,'index':I,'type':S,'text':S,'text_truncated':B,'locator':{'type':'object'},'confidence':nullable({'type':'number','minimum':0,'maximum':1})})
schemas['BusinessFields']=obj({'scope':{'const':'current_document'},'items':array(obj({'key':S,'label':S,'type':S,'value':{'type':['string','boolean','null']},'value_encoding':{'enum':['native','integer-string']},'value_truncated':B,'origin':S,'is_confirmed':B,'source_parse_run_id':nullable(S)})),'total':I,'partial':B})
schemas['AgentContent']=obj({'document_id':S,'document_version':I,'business_fields':ref('BusinessFields'),'content_revision_id':S,'parse_run_id':S,'availability_status':S,'warnings':array(S),'ocr_used':B,
    'stale_for_current_revision':B,'page':I,'page_size':I,'total':I,'blocks':array(ref('AgentBlock'))})
schemas['AgentMarkdown']=obj({'document_id':S,'revision_id':S,'parse_run_id':nullable(S),'format':{'const':'markdown'},'filename':S,'sha256':S,'size_bytes':I,'content_status':{'enum':['content','empty','unavailable']},'refresh_pending':B,'stale_for_current_revision':B,'offset':I,'next_offset':nullable(I),'total_characters':I,'body':S})
schemas['AgentSpaces']=obj({'items':array(obj({'id':S,'name':S}))})
schemas['AgentCatalog']=obj({'folders':array(obj({'id':S,'parent_id':nullable(S),'name':S})),
 'tags':array(obj({'id':S,'name':S})),
 'document_types':array(obj({'id':S,'label':S,'type_key':S,'is_active':B})),
 'fields':array(obj({'key':S,'label':S,'type':S,'constraints':{'type':'object'},'filterable':B,'is_active':B}))})
schemas['AgentSearchResult']=obj({'items':array(obj({'id':S,'space_id':S,'title':S,'document_date':nullable(S),'document_version':I,'current_revision_id':nullable(S),'current_parse_run_id':nullable(S),
 'processing_status':S,'availability_status':S,'content_stale':B,'search_index':{'type':'object'}})),'total':I,'page':I,'page_size':I,'search_index':{'type':'object'}})
schemas['AnalysisContext']=obj({'question':S,'answer_generated':{'const':False},'instructions':S,'documents':array(obj({'overview':ref('Overview'),'evidence':nullable(ref('AgentContent')),'business_fields':ref('BusinessFields')}))})
schemas['AgentTool']=obj({'name':S,'description':S,'inputSchema':{'type':'object'},'annotations':obj({'readOnlyHint':B,'destructiveHint':B,'idempotentHint':B,'openWorldHint':B})})
schemas['AgentCapabilities']=obj({'instructions':S,'formats':{'type':'object'},'tools':array(ref('AgentTool')),'limits':obj({'request_bytes':I,'response_bytes':I,'requests_per_minute':I})})
schemas['McpRequest']={'type':'object','required':['jsonrpc','method'],'properties':{'jsonrpc':{'const':'2.0'},'id':{'type':['string','integer']},'method':S,'params':{'type':'object'}},'additionalProperties':False}
schemas['McpResponse']={'type':'object','required':['jsonrpc','id'],'properties':{'jsonrpc':{'const':'2.0'},'id':{'type':['string','integer','null']},'result':{'type':'object'},'error':{'type':'object'}}}

def parameter(name,location='query',required=True,schema=S):return {'name':name,'in':location,'required':required,'schema':schema}
def operation(summary,response,*,method='get',parameters=None,body=None,session=False,status='200'):
    responses={status:{'description':'Successful read-only result' if status=='200' else 'Credential issued once','content':{'application/json':{'schema':response}}}}
    for code in ('400','401','403','404','409','413','415','422','429','503'):
        responses[code]={'description':'Bounded request, authorization or content error','content':{'application/json':{'schema':ref('Error')}}}
    result={'summary':summary,'security':[{'sessionAuth':[]}] if session else [{'agentBearer':[]},{'sessionAuth':[]},{'bearerAuth':[]}], 'responses':responses}
    if parameters:result['parameters']=parameters
    if body:result['requestBody']={'required':True,'content':{'application/json':{'schema':body}}}
    if session and method!='get':result.setdefault('parameters',[]).append(parameter('X-CSRF-Token','header'))
    return result
paths={}
paths['/agent-tokens']={
 'get':operation('List active scoped agent credentials, never secrets',array(ref('AgentToken')),session=True),
 'post':operation('Create expiring read-only credential with explicit spaces',ref('IssuedAgentToken'),body=ref('TokenInput'),method='post',session=True,status='201')}
paths['/agent-tokens/{id}']={'delete':operation('Revoke credential immediately',{},method='delete',session=True,parameters=[parameter('id','path')],status='204')}
paths['/agent-tokens/{id}']['delete']['responses']['204']={'description':'Credential revoked or already absent'}
paths['/agent/capabilities']={'get':operation('Discover tools, format support and fixed limits',ref('AgentCapabilities'))}
paths['/agent/spaces']={'get':operation('List granted spaces only',ref('AgentSpaces'))}
paths['/agent/catalog']={'get':operation('Read bounded catalog for natural-language filter mapping',ref('AgentCatalog'),parameters=[parameter('space_id')])}
paths['/agent/search']={'post':operation('Literal and structured search; NLU performed by external agent',ref('AgentSearchResult'),method='post',body=ref('AgentSearch'))}
paths['/agent/documents/{id}/overview']={'get':operation('Read source-backed generic overview',ref('Overview'),parameters=[parameter('id','path'),parameter('space_id')])}
paths['/agent/documents/{id}/content']={'get':operation('Read bounded cached blocks with fixed ParseRun pagination',ref('AgentContent'),parameters=[parameter('id','path'),parameter('space_id'),parameter('parse_run_id',required=False),parameter('page',required=False,schema={'type':'integer','minimum':1,'maximum':1000000,'default':1}),parameter('page_size',required=False,schema={'type':'integer','minimum':1,'maximum':20,'default':20})])}
paths['/agent/documents/{id}/markdown']={'get':operation('Read persisted version-bound Markdown; pin revision_id and sha256 across character offsets',ref('AgentMarkdown'),parameters=[parameter('id','path'),parameter('space_id'),parameter('revision_id',required=False),parameter('sha256',required=False,schema={'type':'string','pattern':'^[0-9a-f]{64}$'}),parameter('offset',required=False,schema={'type':'integer','minimum':0,'maximum':16777216,'default':0}),parameter('length',required=False,schema={'type':'integer','minimum':1,'maximum':32000,'default':16000})])}
paths['/agent/analysis-templates']={'get':operation('Discover five versioned business templates and submission schema',{'type':'object'})}
paths['/agent/imports/{request_id}']={'post':operation('Import raw original with explicitly enabled scoped credential; always queue local parsing',{'type':'object'},method='post',parameters=[parameter('request_id','path',schema={'type':'string','pattern':'^[A-Za-z0-9_-]{1,100}$'}),parameter('space_id'),parameter('filename',schema={'type':'string','minLength':1,'maxLength':255})],status='201')}
paths['/agent/imports/{request_id}']['post']['requestBody']={'required':True,'content':{'application/octet-stream':{'schema':{'type':'string','format':'binary'}}}}
paths['/agent/imports/{id}/analyses']={'post':operation('Submit immutable version/hash-bound external analysis; exact quotes validate against Agent Markdown, not original semantics',{'type':'object'},method='post',parameters=[parameter('id','path')],body=ref('Submission'),status='201')}
for path in ('/agent/imports/{request_id}','/agent/imports/{id}/analyses'):
    paths[path]['post']['security']=[{'agentBearer':[]}]
    paths[path]['post']['description']='Requires administrator-created import_enabled=true credential and granted space. OAuth and existing read-only tokens do not gain write permissions.'
paths['/agent/documents/{id}/analyses']={'get':operation('Read retained external analysis, one record per page; current original preferred',{'type':'object'},parameters=[parameter('id','path'),parameter('space_id'),parameter('page',required=False,schema={'type':'integer','minimum':1,'maximum':10000,'default':1})])}
paths['/agent/analysis-context']={'post':operation('Prepare question and cited evidence; does not generate an answer',ref('AnalysisContext'),method='post',body=ref('AnalysisInput'))}
paths['/documents/{id}/overview']={'get':operation('Shared Web/agent overview, including explicit historical ParseRun',ref('Overview'),parameters=[parameter('id','path'),parameter('parse_run_id',required=False)])}
paths['/documents/{id}/overview']['get']['security']=[{'sessionAuth':[]},{'bearerAuth':[]}]
mcp=operation('MCP JSON-RPC Streamable HTTP, modern and legacy tools',ref('McpResponse'),method='post',body=ref('McpRequest'),parameters=[parameter('Accept','header'),parameter('MCP-Protocol-Version','header',False),parameter('Mcp-Method','header',False),parameter('Mcp-Name','header',False),parameter('Origin','header',False)])
mcp['security']=[{'agentBearer':[]}];mcp['description']='Versions 2026-07-28, 2025-11-25, 2025-06-18. See AGENT-API.md for metadata/header consistency. No OAuth automation or legacy SSE.'
mcp['responses']['202']={'description':'Accepted supported legacy notification; no body'}
for status in ('400','404','406'):mcp['responses'][status]={'description':'MCP protocol error','content':{'application/json':{'schema':ref('McpResponse')}}}
paths['/agent/mcp']={'post':mcp}
value={'openapi':'3.1.0','info':{'title':'JuanZhan Agent API extension','version':'0.4.38'},'servers':[{'url':'/api/v1'}],'paths':paths,
       'components':{'schemas':schemas,'securitySchemes':{'agentBearer':{'type':'http','scheme':'bearer','description':'Scoped jza_ read-only credential'},'sessionAuth':{'type':'apiKey','in':'cookie','name':'archive_session'},'bearerAuth':{'type':'http','scheme':'bearer'}}}}
output=ROOT/'docs/reference/agent-openapi.json';output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
print('Agent OpenAPI paths:',len(paths))
if __name__=='__main__':pass
