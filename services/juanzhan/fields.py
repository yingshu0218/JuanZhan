"""Space-scoped field definitions. Value typing and constraint evaluation belong to T18."""
import json
import uuid
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import Field, field_validator

from .auth import fail
from .catalog import ID, Input, Name, Patch, TypeKey, now, required, scope, transaction

FieldType = Literal['text','long_text','integer','decimal','date','boolean','single_select']
MAX_FIELDS_PER_SPACE = 1000
MAX_CONSTRAINT_BYTES = 16384


def constraint_object(value):
    # The V0.4 contract leaves rule vocabulary open. Preserve JSON verbatim, but bound
    # its storage/serialization cost; never silently claim these rules are evaluated.
    try:
        def visit(node,depth=0):
            if depth>8:raise ValueError('Constraints nesting exceeds the limit')
            if isinstance(node,dict):
                for child in node.values():visit(child,depth+1)
            elif isinstance(node,list):
                for child in node:visit(child,depth+1)
        visit(value)
        text=json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'),sort_keys=True)
        if len(text.encode('utf-8'))>MAX_CONSTRAINT_BYTES:raise ValueError('Constraints exceed 16 KiB')
    except (TypeError,UnicodeError,RecursionError) as exc:
        raise ValueError('Constraints must contain bounded JSON') from exc
    return value


class FieldCreate(Input):
    space_id: ID
    key: TypeKey
    label: Name
    type: FieldType
    constraints: dict = Field(default_factory=dict)
    searchable: bool = Field(default=False,strict=True)
    filterable: bool = Field(default=False,strict=True)

    @field_validator('constraints')
    @classmethod
    def rules(cls,value):return constraint_object(value)


class FieldPatch(Patch):
    label: Name | None = None
    constraints: dict | None = None
    searchable: bool | None = Field(default=None,strict=True)
    filterable: bool | None = Field(default=None,strict=True)
    is_active: bool | None = Field(default=None,strict=True)

    @field_validator('constraints')
    @classmethod
    def rules(cls,value):return constraint_object(value)


def public(row):
    return {'id':row['id'],'space_id':row['space_id'],'key':row['field_key'],'label':row['label'],
            'type':row['field_type'],'constraints':json.loads(row['constraints_json']),
            **{key:bool(row[key]) for key in ('searchable','filterable','is_active')}}


def router(settings):
    routes=APIRouter(prefix='/api/v1/field-definitions')

    @routes.get('')
    def definitions(space_id: ID | None=None):
        with transaction(settings) as db:
            scope(db,space_id)
            return [public(row) for row in db.execute('SELECT * FROM field_definitions WHERE (? IS NULL OR space_id=?) '
                                                      'ORDER BY space_id,field_key,id',(space_id,space_id))]

    @routes.post('',status_code=201)
    def create(body: FieldCreate,request: Request):
        with transaction(settings,request) as db:
            required(db,'spaces',body.space_id)
            if db.execute('SELECT count(*) FROM field_definitions WHERE space_id=?',(body.space_id,)).fetchone()[0]>=MAX_FIELDS_PER_SPACE:
                fail(409,'FIELD_LIMIT_REACHED','Space has reached its field definition limit')
            id=uuid.uuid4().hex
            db.execute('INSERT INTO field_definitions(id,space_id,field_key,label,field_type,constraints_json,searchable,filterable,is_active,created_at) '
                       'VALUES (?,?,?,?,?,?,?,?,1,?)',
                       (id,body.space_id,body.key,body.label,body.type,json.dumps(body.constraints,ensure_ascii=False,allow_nan=False),
                        int(body.searchable),int(body.filterable),now()))
            return public(required(db,'field_definitions',id))

    @routes.patch('/{id}')
    def update(id: str,body: FieldPatch,request: Request):
        with transaction(settings,request) as db:
            required(db,'field_definitions',id)
            values=body.model_dump(exclude_unset=True)
            columns=[];parameters=[]
            for key,value in values.items():
                columns.append(('constraints_json' if key=='constraints' else key)+'=?')
                parameters.append(json.dumps(value,ensure_ascii=False,allow_nan=False) if key=='constraints' else value)
            db.execute('UPDATE field_definitions SET '+','.join(columns)+' WHERE id=?',(*parameters,id))
            return public(required(db,'field_definitions',id))
    return routes
