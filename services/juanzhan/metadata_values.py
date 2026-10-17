"""Exact typed metadata and filing checks, shared by HTTP and batch mutations."""
import json
import re
from datetime import date
from decimal import Decimal

import regex

from .auth import fail

COLUMNS={'text':'value_text','long_text':'value_text','single_select':'value_text','integer':'value_integer',
         'decimal':'value_decimal_scaled','date':'value_date','boolean':'value_bool'}


def invalid(code='INVALID_METADATA_VALUE'):
    fail(422,code,'Metadata value or field rule is invalid')


def scalar(kind,value):
    if kind in ('text','long_text','single_select'):
        if not isinstance(value,str) or len(value)>65536:invalid()
        try:value.encode('utf-8')
        except UnicodeError:invalid()
        return value
    if kind=='integer':
        if type(value) is not int or not -9223372036854775808<=value<=9223372036854775807:invalid()
        return value
    if kind=='boolean':
        if type(value) is not bool:invalid()
        return value
    if kind=='date':
        if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):invalid()
        try:date.fromisoformat(value)
        except ValueError:invalid()
        return value
    if kind=='decimal':
        if not isinstance(value,str) or len(value)>32 or not re.fullmatch(r'-?\d+(?:\.\d{1,4})?',value,flags=re.ASCII):invalid()
        scaled=Decimal(value)*10000
        if abs(scaled)>90000000000000000:invalid()
        return int(scaled)
    invalid()


def rules(kind,config,*,legacy=False):
    allowed={'text':{'min_length','max_length','regex'},'long_text':{'min_length','max_length','regex'},
             'integer':{'min','max'},'decimal':{'min','max'},'date':{'min','max'},'boolean':set(),'single_select':{'options'}}[kind]
    if not isinstance(config,dict) or set(config)-allowed:
        if legacy:fail(501,'FIELD_RULES_NOT_IMPLEMENTED','Unknown field rules require explicit configuration repair')
        invalid('INVALID_FIELD_RULES')
    for name,value in config.items():
        if name in ('min','max'):scalar(kind,value)
        elif name in ('min_length','max_length'):
            if type(value) is not int or not 0<=value<=65536:invalid('INVALID_FIELD_RULES')
        elif name=='regex':
            if not isinstance(value,str) or len(value)>512:invalid('INVALID_FIELD_RULES')
            if any(int(n)>65536 for n in re.findall(r'(?<=[{,])[0-9]+(?=[,}])',value)):invalid('INVALID_FIELD_RULES')
            try:regex.compile(value)
            except (regex.error,OverflowError):invalid('INVALID_FIELD_RULES')
        elif name=='options':
            if not isinstance(value,list) or not 1<=len(value)<=1000:invalid('INVALID_FIELD_RULES')
            ids=[]
            for item in value:
                if not isinstance(item,dict) or set(item)!={'id','label'}:invalid('INVALID_FIELD_RULES')
                if any(not isinstance(item[k],str) or not item[k].strip() or len(item[k])>255 for k in ('id','label')):invalid('INVALID_FIELD_RULES')
                ids.append(item['id'])
            if len(ids)!=len(set(ids)):invalid('INVALID_FIELD_RULES')
    if 'min' in config and 'max' in config and scalar(kind,config['min'])>scalar(kind,config['max']):invalid('INVALID_FIELD_RULES')
    if config.get('min_length',0)>config.get('max_length',65536):invalid('INVALID_FIELD_RULES')
    return config


def validate(field,value):
    kind=field['field_type'];config=rules(kind,json.loads(field['constraints_json']),legacy=True)
    typed=scalar(kind,value)
    if 'min' in config and typed<scalar(kind,config['min']):invalid()
    if 'max' in config and typed>scalar(kind,config['max']):invalid()
    if isinstance(value,str):
        if len(value)<config.get('min_length',0) or len(value)>config.get('max_length',65536):invalid()
    if 'regex' in config:
        try:
            if regex.fullmatch(config['regex'],value,timeout=0.02) is None:invalid()
        except TimeoutError:invalid('FIELD_RULE_TIMEOUT')
        except regex.error:invalid('INVALID_FIELD_RULES')
    if kind=='single_select' and value not in {item['id'] for item in config.get('options',[])}:invalid()
    return COLUMNS[kind],int(typed) if kind=='boolean' else typed


def value(field,row):
    raw=row[COLUMNS[field['field_type']]]
    if field['field_type']=='decimal':return format(Decimal(raw)/10000,'.4f')
    if field['field_type']=='boolean':return bool(raw)
    return raw


def entries(db,id):
    result=[]
    for row in db.execute('SELECT m.*,f.field_key,f.field_type FROM metadata_values m JOIN field_definitions f ON f.id=m.field_definition_id WHERE m.document_id=? ORDER BY f.field_key,f.id',(id,)):
        result.append({'field_definition_id':row['field_definition_id'],'key':row['field_key'],'value':value(row,row),
                       'origin':row['origin'],'is_confirmed':bool(row['is_confirmed']),
                       'source_parse_run_id':row['source_parse_run_id'],'updated_at':row['updated_at']})
    return result


def filing(db,record):
    if record['document_type_id'] is None:return
    fields=db.execute('SELECT f.*,t.required_for_filing FROM document_type_fields t JOIN field_definitions f ON f.id=t.field_definition_id WHERE t.document_type_id=?',(record['document_type_id'],)).fetchall()
    for field in fields:
        row=db.execute('SELECT * FROM metadata_values WHERE document_id=? AND field_definition_id=?',(record['id'],field['id'])).fetchone()
        if row is None or (field['field_type'] in ('text','long_text','single_select') and not row['value_text'].strip()):
            if field['required_for_filing']:fail(422,'MISSING_REQUIRED_FIELDS','Required metadata is missing')
        if row is not None:validate(field,value(field,row))
