"""Keep the public extension references and shipped tool schemas internally resolvable."""
import json
from pathlib import Path
from juanzhan.apps import create_app
from juanzhan.agent_api import tools

ROOT=Path(__file__).resolve().parents[1]

def check_refs(value,document):
    if isinstance(value,dict):
        if '$ref' in value:
            ref=value['$ref'];assert ref.startswith('#/')
            item=document
            for part in ref[2:].split('/'):item=item[part.replace('~1','/').replace('~0','~')]
        for child in value.values():check_refs(child,document)
    elif isinstance(value,list):
        for child in value:check_refs(child,document)

def test_openapi_extension_paths_are_registered_and_refs_resolve():
    schema=json.loads((ROOT/'docs/reference/agent-openapi.json').read_text());check_refs(schema,schema)
    runtime=create_app('archive').openapi()['paths']
    main=(ROOT/'docs/reference/archive-openapi-v0.4.yaml').read_text()
    for path,item in schema['paths'].items():
        assert '/api/v1'+path in runtime
        assert 'agent-openapi.json#/paths/'+path.replace('~','~0').replace('/','~1') in main
        for method in item:assert method in runtime['/api/v1'+path]

def test_every_agent_tool_schema_is_closed_and_read_only():
    for tool in tools():
        check_refs(tool['inputSchema'],tool['inputSchema'])
        assert tool['inputSchema']['additionalProperties'] is False
        assert tool['annotations']=={'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}

def test_oauth_extension_paths_and_root_server_overrides():
    schema=json.loads((ROOT/'docs/reference/oauth-openapi.json').read_text());check_refs(schema,schema)
    runtime=create_app('archive').openapi()['paths']
    main=(ROOT/'docs/reference/archive-openapi-v0.4.yaml').read_text()
    for path,item in schema['paths'].items():
        assert path in runtime
        assert item['servers']==[{'url':'/'}]
        assert 'oauth-openapi.json#/paths/'+path.replace('~','~0').replace('/','~1') in main
        for method in item:
            if method!='servers':assert method in runtime[path]
