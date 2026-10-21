"""Published source/version/storage schemas must match generated and routed behavior."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
from test_agent_contract import check_refs
from juanzhan.apps import create_app
from juanzhan.source_files import SourceRequest,SourceMigration
from juanzhan.storage_management import Cleanup,DeleteRevision

ROOT=Path(__file__).resolve().parents[1]


def test_source_extension_routes_refs_and_input_schemas_match():
    schema=json.loads((ROOT/'docs/reference/source-files-openapi.json').read_text())
    check_refs(schema,schema)
    runtime=create_app('archive').openapi()['paths']
    main=(ROOT/'docs/reference/archive-openapi-v0.4.yaml').read_text()
    assert len(schema['paths'])==8
    for path,operations in schema['paths'].items():
        assert 'source-files-openapi.json#/paths/'+path.replace('/','~1') in main
        for method,operation in operations.items():
            assert method in runtime['/api/v1'+path]
            assert operation['security']==[{'sessionAuth':[]},{'bearerAuth':[]}]
    for cls in (SourceRequest,SourceMigration,Cleanup,DeleteRevision):
        assert schema['components']['schemas'][cls.__name__]==cls.model_json_schema()


def test_source_extension_is_reproducibly_generated(tmp_path):
    (tmp_path/'services').symlink_to(ROOT/'services',target_is_directory=True)
    (tmp_path/'scripts').mkdir();(tmp_path/'docs/reference').mkdir(parents=True)
    shutil.copy(ROOT/'scripts/generate_source_files_openapi.py',tmp_path/'scripts')
    shutil.copy(ROOT/'docs/reference/agent-openapi.json',tmp_path/'docs/reference')
    subprocess.run([sys.executable,str(tmp_path/'scripts/generate_source_files_openapi.py')],check=True,capture_output=True)
    assert json.loads((tmp_path/'docs/reference/source-files-openapi.json').read_text())==json.loads((ROOT/'docs/reference/source-files-openapi.json').read_text())
