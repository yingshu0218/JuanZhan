"""Export the generic scoped REST import profile; excludes all management paths."""
import copy
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def profile():
    source=json.loads((ROOT/'docs/reference/agent-openapi.json').read_text())
    value=copy.deepcopy(source)
    value['info']={'title':'JuanZhan read-only document REST API','version':'0.4.31',
        'description':'External agents provide NLU and synthesis. Use a scoped agent Bearer token, issued manually or through the separate OAuth discovery/PKCE flow. No uploads, writes or arbitrary URLs. See AGENT-API.md.'}
    value['paths']={path:item for path,item in value['paths'].items() if path.startswith('/agent/') and path!='/agent/mcp'}
    for item in value['paths'].values():
        for operation in item.values():operation['security']=[{'agentBearer':[]}]
    value['components']['securitySchemes']={'agentBearer':source['components']['securitySchemes']['agentBearer']}
    return value

if __name__=='__main__':
    (ROOT/'docs/reference/agent-rest-openapi.json').write_text(json.dumps(profile(),ensure_ascii=False,indent=2)+'\n')
