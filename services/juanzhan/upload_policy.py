"""Instance upload policy. Upload admission only; existing originals are never deleted."""
import json
from pathlib import Path
from typing import Annotated
from fastapi import APIRouter,Request,Response
from pydantic import Field,model_validator
from .auth import fail
from .catalog import Input,transaction
from .database import connect

GROUPS=json.loads(Path(__file__).with_name('upload_formats.json').read_text())['groups']
IDS={g['id'] for g in GROUPS}
DEFAULT={'excluded_groups':[g['id'] for g in GROUPS if g['default_excluded']],'custom_extensions':[]}
class PolicyInput(Input):
    expected_version:Annotated[int,Field(strict=True,ge=1)]
    excluded_groups:list[Annotated[str,Field(min_length=1,max_length=80)]]=Field(max_length=30)
    custom_extensions:list[Annotated[str,Field(pattern=r'^[a-z0-9][a-z0-9._+-]{0,19}$')]]=Field(default_factory=list,max_length=100)
    @model_validator(mode='after')
    def choices(self):
        if set(self.excluded_groups)-IDS:raise ValueError('Unknown upload group')
        self.excluded_groups=sorted(set(self.excluded_groups))
        self.custom_extensions=sorted(set(self.custom_extensions))
        return self

def read(db):
    version,raw=db.execute('SELECT version,config_json FROM upload_policy WHERE id=1').fetchone()
    return {'version':version,**json.loads(raw),'groups':GROUPS}

def reason(filename,policy):
    name=filename.casefold()
    for extension in policy['custom_extensions']:
        if name.endswith('.'+extension):return '自定义排除格式'
    for group in GROUPS:
        if group['id'] not in policy['excluded_groups']:continue
        if (any(name.endswith('.'+e) for e in group.get('extensions',[])) or
            name in {n.casefold() for n in group.get('files',[])} or
            any(name.startswith(p) for p in group.get('prefixes',[]))):return group['label']
    return None

def check(db,filename):
    if reason(filename,read(db)):fail(422,'UPLOAD_FORMAT_EXCLUDED','File format is excluded by the current upload policy')

def check_file(settings,filename):
    with connect(settings.database) as db:check(db,filename)

def router(settings):
    routes=APIRouter(prefix='/api/v1/system')
    @routes.get('/upload-policy')
    def get_policy(response:Response):
        response.headers["Cache-Control"]="no-store"
        with transaction(settings) as db:return read(db)
    @routes.put('/upload-policy')
    def update_policy(body:PolicyInput,request:Request):
        with transaction(settings,request) as db:
            if read(db)['version']!=body.expected_version:fail(409,'UPLOAD_POLICY_CONFLICT','Upload policy changed; reload before saving')
            value=body.model_dump(exclude={'expected_version'})
            db.execute('UPDATE upload_policy SET version=version+1,config_json=? WHERE id=1',(json.dumps(value),))
            return read(db)
    return routes
