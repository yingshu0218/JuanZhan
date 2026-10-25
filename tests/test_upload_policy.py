"""Real upload admission, live config, Agent scope and backup persistence."""
import pytest
from test_parsing import pipeline
from test_agent_imports import token,imported,ROOT
from juanzhan.database import connect

def put(pipeline,name,data=b'test'):
 _,client,csrf,space=pipeline
 return client.post('/api/v1/documents/upload',headers=csrf,data={'space_id':space},files={'file':(name,data,'application/octet-stream')})

@pytest.mark.parametrize('name',['data.json','DATA.JSON','config.yaml','package-lock.json','.env.production','main.py','bundle.js','setup.exe','archive.zip','cache.sqlite','run.log'])
def test_defaults_reject_before_registering_original(pipeline,name):
 settings,client,_,_=pipeline
 response=put(pipeline,name)
 assert response.status_code==422 and response.json()['error']['code']=='UPLOAD_FORMAT_EXCLUDED',response.text
 with connect(settings.database) as db:
  assert db.execute('select count(*) from documents').fetchone()[0]==0
  assert db.execute('select count(*) from managed_objects').fetchone()[0]==0

@pytest.mark.parametrize('name',['notes.txt','README.md','report.pdf','contract.docx','data.csv','photo.jpg','table.xlsx','deck.pptx','page.html','book.epub'])
def test_common_document_names_remain_accepted(pipeline,name):
 assert put(pipeline,name).status_code==201

def test_live_config_scope_csrf_conflict_and_backup(pipeline,tmp_path):
 from juanzhan.backup import create,restore
 settings,client,csrf,space=pipeline
 policy=client.get('/api/v1/system/upload-policy').json()
 body={'expected_version':policy['version'],'excluded_groups':[g for g in policy['excluded_groups'] if g!='structured_data'],'custom_extensions':['psd']}
 assert client.put('/api/v1/system/upload-policy',json=body).status_code==403
 saved=client.put('/api/v1/system/upload-policy',headers=csrf,json=body)
 assert saved.status_code==200,saved.text
 assert client.put('/api/v1/system/upload-policy',headers=csrf,json=body).status_code==409
 assert put(pipeline,'data.json',b'{"title":"sample"}').status_code==201
 assert put(pipeline,'design.psd').status_code==422
 _,h=token(pipeline)
 assert client.get('/api/v1/system/upload-policy',headers=h).status_code==403
 assert imported(pipeline,h,name='another.json',data=b'{}').status_code==201
 assert imported(pipeline,h,name='main.py',key='rejected').status_code==422
 catalog=client.get(ROOT+'/analysis-templates',headers=h).json()
 assert 'structured_data' not in catalog['upload_policy']['excluded_groups']
 assert client.put('/api/v1/system/upload-policy',headers=csrf,json={**body,'expected_version':saved.json()['version'],'excluded_groups':['unknown']}).status_code==422
 bundle=tmp_path/'policy-backup';create(settings,bundle);restore(bundle,tmp_path/'restored')
 with connect(tmp_path/'restored/database/archive.sqlite3') as db:
  import json
  row=db.execute('select config_json from upload_policy').fetchone()
  assert json.loads(row[0])['custom_extensions']==['psd']


def test_agent_default_rejects_json_and_static_auxiliary_cannot_be_enabled(pipeline):
 _,client,csrf,_=pipeline;_,h=token(pipeline)
 assert imported(pipeline,h,name='data.json',data=b'{}').status_code==422
 policy=client.get('/api/v1/system/upload-policy').json()
 assert client.put('/api/v1/system/upload-policy',headers=csrf,json={'expected_version':policy['version'],'excluded_groups':[],'custom_extensions':[]}).status_code==200
 assert put(pipeline,'.DS_Store').status_code==422
 assert put(pipeline,'.gitignore').status_code==422
