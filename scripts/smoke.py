"""Validate the running Compose services without exposing the service token."""
import json
import subprocess
import urllib.request

with urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=5) as response:
    assert json.load(response) == {'status': 'ok'}
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
    assert json.load(r) == {'schema_versions':[], 'supported_input_types':[], 'ocr_available':False}
try:
    urllib.request.urlopen(urllib.request.Request(base+'/v1/jobs', data=b'', headers=headers), timeout=5)
except urllib.error.HTTPError as e:
    assert e.code == 501
else:
    raise AssertionError('Unimplemented job accepted')
'''], check=True)
print('PASS: Archive readiness; Converter authentication, empty capabilities and 501 boundary')

subprocess.run(['docker','compose','exec','-T','archive-worker','python','-m','juanzhan.worker','--healthcheck'],check=True)
print('PASS: Archive worker heartbeat health')
