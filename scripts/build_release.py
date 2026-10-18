"""Build a local candidate; never publishes or changes existing Compose services."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    version=(ROOT/'VERSION').read_text().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-rc\.\d+)?',version):raise ValueError('Invalid version')
    env=dict(os.environ);env.setdefault('DOCKER_CONFIG',str(ROOT/'.local/docker'))
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT))
    tag='juanzhan:'+version
    subprocess.run(['npm','run','build'],cwd=ROOT/'web',env=env,check=True)
    subprocess.run(['docker','build','--build-arg','VERSION='+version,'--build-arg','REVISION='+revision,
        '--build-arg','SOURCE_DIRTY='+str(dirty).lower(),'-t',tag,'.'],cwd=ROOT,env=env,check=True)
    image=json.loads(subprocess.check_output(['docker','image','inspect',tag],env=env))[0]
    report={'version':version,'tag':tag,'image_id':image['Id'],'source_revision':revision,'source_dirty':dirty,
            'architecture':image['Architecture'],'os':image['Os'],'published':False}
    output=Path(tempfile.mkdtemp(prefix='juanzhan-release-'))/'manifest.json'
    output.write_text(json.dumps(report,indent=2)+'\n')
    print('Local candidate built; manifest: '+str(output))
if __name__=='__main__':main()
