"""Generate the precise source/version/reading/storage extension, without a running DB."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services'))
from juanzhan.source_files import SourceRequest,SourceMigration
from juanzhan.storage_management import Cleanup,DeleteRevision

def reference(name):return {'$ref':'#/components/schemas/'+name}
def obj(properties,required=None):return {'type':'object','properties':properties,'required':list(properties) if required is None else required,'additionalProperties':False}
def array(items):return {'type':'array','items':items}
S={'type':'string'};N={'type':'integer','minimum':0};B={'type':'boolean'};NULL={'type':'null'}
schemas={c.__name__:c.model_json_schema() for c in (SourceRequest,SourceMigration,Cleanup,DeleteRevision)}
schemas['Error']=json.loads((ROOT/'docs/reference/agent-openapi.json').read_text())['components']['schemas']['Error']
schemas['Job']=obj({'job_id':S,'status':S})
schemas['SourceLink']=obj({'id':S,'name':S,'status':S,'entry_status':S,'relative_path':S})
schemas['SourceVersion']=obj({**{key:S for key in ('id','original_filename','mime_type','sha256','created_at','storage_kind','availability_status')},
 'revision_no':{'type':'integer','minimum':1},'size_bytes':N,'is_current':B,'server_copy':B,'source':{'oneOf':[reference('SourceLink'),NULL]}})
schemas['SourceInventory']=obj({'document_id':S,'document_version':{'type':'integer','minimum':1},'current_revision_id':{'type':['string','null']},
 'items':array(reference('SourceVersion')),'page':{'type':'integer','minimum':1},'page_size':{'type':'integer','minimum':1,'maximum':50},'total':N})
schemas['ReadingPreview']=obj({'revision_id':S,'state':{'enum':['ready','queued','running','failed','not_generated']},'supported':B,
 'job_id':{'type':['string','null']},'renderer':{'type':['string','null']},'created_at':{'type':['string','null']}})
schemas['Storage']=obj({**{key:N for key in ('physical_original_bytes','physical_derived_bytes','current_original_bytes','historical_original_bytes',
 'external_snapshot_bytes','reading_preview_bytes','original_revisions','external_revisions_without_snapshot','reading_preview_count','trash_documents','gc_retention_seconds')},
 'accounting':{'const':'registered_objects'},'note':S})
paths={}
def parameter(name,location='query',required=True,schema=None,description=None):
 value={'in':location,'name':name,'required':required,'schema':schema or S}
 if description:value['description']=description
 return value
def operation(path,method,summary,result,status='200',body=None,parameters=None):
 response={'description':'Success','content':{'application/json':{'schema':result}}}
 value={'summary':summary,'security':[{'sessionAuth':[]},{'bearerAuth':[]}],'responses':{status:response},'parameters':parameters or []}
 if '{id}' in path:value['parameters'].insert(0,parameter('id','path'))
 if '{revision_id}' in path:value['parameters'].append(parameter('revision_id','path'))
 if body:
  value['requestBody']={'required':True,'content':{'application/json':{'schema':reference(body)}}}
  value['parameters'].append(parameter('X-CSRF-Token','header',False,description='Required with Cookie authentication; not used with administrator Bearer authentication.'))
 for code in ('401','403','404','409','413','422','429','503'):
  value['responses'][code]={'description':'Authentication, version, provenance, budget or resource rejection','content':{'application/json':{'schema':reference('Error')}}}
 paths.setdefault(path,{})[method]=value
operation('/documents/{id}/source-files','get','List registered original versions and external snapshot state',reference('SourceInventory'),parameters=[
 parameter('page',required=False,schema={'type':'integer','minimum':1,'maximum':1000000,'default':1}),
 parameter('page_size',required=False,schema={'type':'integer','minimum':1,'maximum':50,'default':20})])
operation('/documents/{id}/source-snapshot','post','Queue a verified readonly external original copy without switching origin',reference('Job'),'202','SourceRequest')
operation('/sources/{id}/source-snapshots','post','Queue paginated durable snapshot migration for current external originals',reference('Job'),'202','SourceMigration')
operation('/documents/{id}/reading-preview','get','Read the selected version reading-preview state',reference('ReadingPreview'),parameters=[parameter('revision_id',required=False,schema={'type':'string','minLength':1,'maxLength':255})])
operation('/documents/{id}/reading-preview','post','Queue an Office or TIFF reading PDF without reparsing or replacing the original',reference('Job'),'202','SourceRequest')
operation('/documents/{id}/reading-preview/file','get','Read a verified selected-version reading PDF as passive attachment',{},parameters=[parameter('revision_id',schema={'type':'string','minLength':1,'maxLength':255})])
paths['/documents/{id}/reading-preview/file']['get']['responses']['200']={'description':'Verified bounded PDF bytes; no-store, nosniff, attachment; X-Revision-ID pins the source revision',
 'headers':{'X-Revision-ID':{'schema':S}},'content':{'application/octet-stream':{'schema':{'type':'string','format':'binary'}}}}
operation('/system/storage','get','Read registered object accounting, with deduplicated and overlapping logical classifications',reference('Storage'))
operation('/system/storage/cleanup','post','Queue bounded cache cleanup and delayed reference-aware garbage collection',reference('Job'),'202','Cleanup')
operation('/documents/{id}/revisions/{revision_id}','delete','Explicitly remove an unprotected historical version; never delete an external file',reference('Job'),'202','DeleteRevision')
value={'openapi':'3.1.0','info':{'title':'JuanZhan source files and storage extension','version':'0.4.32'},'servers':[{'url':'/api/v1'}],
 'paths':paths,'components':{'securitySchemes':{'sessionAuth':{'type':'apiKey','in':'cookie','name':'archive_session'},'bearerAuth':{'type':'http','scheme':'bearer'}},'schemas':schemas}}
(ROOT/'docs/reference/source-files-openapi.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
print('Generated '+str(len(paths))+' source/storage paths')
