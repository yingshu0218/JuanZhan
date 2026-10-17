"""Fetch only pinned official OCR models, verifying TLS, length and SHA256."""
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

def main():
    target = ROOT/'ocr-models'
    target.mkdir(exist_ok=True)
    for model in json.loads((ROOT/'ocr-models.lock.json').read_text())['models']:
        path = target/(model['language']+'.traineddata')
        def valid(data):
            return len(data)==model['size_bytes'] and hashlib.sha256(data).hexdigest()==model['sha256']
        if path.exists() and valid(path.read_bytes()):
            continue
        if '--verify' in sys.argv:
            raise SystemExit('Missing or invalid OCR model: '+model['language'])
        with urllib.request.urlopen(model['url'], timeout=60) as response:
            data = response.read(model['size_bytes']+1)
        if not valid(data):
            raise SystemExit('OCR model integrity failure: '+model['language'])
        temporary = path.with_suffix('.part')
        temporary.write_bytes(data)
        temporary.replace(path)
    print('OCR models verified: eng, chi_sim')

if __name__=='__main__':
    main()
