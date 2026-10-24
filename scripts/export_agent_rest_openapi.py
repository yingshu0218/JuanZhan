"""Export the generic scoped REST import profile; excludes all management paths."""
import copy
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def profile():
    source=json.loads((ROOT/'docs/reference/agent-openapi.json').read_text())
    value=copy.deepcopy(source)
    value['info']={'title':'JuanZhan read-only document REST API','version':'0.4.37',
        'description':'External agents provide NLU and synthesis. Use a scoped agent Bearer token, issued manually or through the separate OAuth discovery/PKCE flow. No uploads, writes or arbitrary URLs. See AGENT-API.md.'}
    value['paths']={path:item for path,item in value['paths'].items() if path.startswith('/agent/') and path!='/agent/mcp' and not path.startswith('/agent/imports/')}
    for item in value['paths'].values():
        for operation in item.values():operation['security']=[{'agentBearer':[]}]
    value['components']['securitySchemes']={'agentBearer':source['components']['securitySchemes']['agentBearer']}
    return value

def import_profile():
    value=profile()
    source=json.loads((ROOT/'docs/reference/agent-openapi.json').read_text())
    value['info']={'title':'JuanZhan opt-in Agent import and analysis API','version':'0.4.37',
        'description':'Requires an administrator-created scoped import_enabled=true Bearer credential. Existing read-only or OAuth credentials do not gain writes. Preserve original bytes; submit version/hash-bound external analysis. No internal model.'}
    value['paths']={path:copy.deepcopy(item) for path,item in source['paths'].items() if path.startswith('/agent/imports/') or path in ('/agent/spaces','/agent/analysis-templates','/agent/documents/{id}/analyses')}
    for item in value['paths'].values():
        for operation in item.values():operation['security']=[{'agentBearer':[]}]
    return value

if __name__=='__main__':
    (ROOT/'docs/reference/agent-rest-openapi.json').write_text(json.dumps(profile(),ensure_ascii=False,indent=2)+'\n')
    (ROOT/'docs/reference/agent-import-openapi.json').write_text(json.dumps(import_profile(),ensure_ascii=False,indent=2)+'\n')
