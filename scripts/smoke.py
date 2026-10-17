"""Validate the running Compose services without exposing the service token."""
import json
import re
import subprocess
import urllib.request

with urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=5) as response:
    assert json.load(response) == {'status': 'ok'}
with urllib.request.urlopen('http://127.0.0.1:8000/',timeout=5) as response:
    html=response.read().decode()
    assert response.status==200 and 'JuanZhan' in html
    assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']
asset=re.search(r'src="(/assets/[^"]+\.js)"',html).group(1)
with urllib.request.urlopen('http://127.0.0.1:8000'+asset,timeout=5) as response:
    assert response.status==200 and len(response.read())>0
print('PASS: public Web shell/CSP and compiled assets')
subprocess.run(['docker', 'compose', 'exec', '-T', 'converter', 'python', '-c', '''
import json, os, urllib.request, urllib.error
base='http://127.0.0.1:8000'
try:
    urllib.request.urlopen(base+'/v1/capabilities', timeout=5)
except urllib.error.HTTPError as e:
    assert e.code == 401
else:
    raise AssertionError('Unauthenticated request accepted')
headers={'Authorization':'Bearer '+os.environ['CONVERTER_SERVICE_TOKEN']}
with urllib.request.urlopen(urllib.request.Request(base+'/v1/capabilities', headers=headers), timeout=5) as r:
    cap=json.load(r)
    from juanzhan.conversion_formats import SUPPORTED
    assert cap['schema_versions']==['1.0'] and cap['supported_input_types']==SUPPORTED and not cap['ocr_available']
try:
    urllib.request.urlopen(urllib.request.Request(base+'/v1/jobs', data=b'', headers=headers), timeout=5)
except urllib.error.HTTPError as e:
    assert e.code == 400
else:
    raise AssertionError('Invalid multipart job accepted')
'''], check=True)
print('PASS: Archive readiness; Converter authentication, six-format capabilities and multipart boundary')

subprocess.run(['docker','compose','exec','-T','archive-worker','python','-m','juanzhan.worker','--healthcheck'],check=True)
print('PASS: Archive worker heartbeat health')
