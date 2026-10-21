"""Real retained fixture matrix against an explicitly configured private renderer."""
import argparse
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError,URLError
from urllib.request import Request,build_opener,ProxyHandler

parser=argparse.ArgumentParser()
parser.add_argument('--fixtures',type=Path,required=True)
parser.add_argument('--modern',type=Path,required=True)
parser.add_argument('--report',type=Path,required=True)
args=parser.parse_args()
base=os.environ['OFFICE_PREVIEW_URL'].rstrip('/')
token=os.environ['CONVERTER_SERVICE_TOKEN']
opener=build_opener(ProxyHandler({}))
for attempt in range(30):
    try:
        with opener.open(base+'/healthz',timeout=1):break
    except OSError:
        if attempt==29:raise
        time.sleep(.2)
root=args.fixtures;modern=args.modern
cases=[(root/'LibreOfficeWriter_odt_1.3.odt','application/vnd.oasis.opendocument.text'),
 (root/'LibreOfficeCalc_ods_1.3.ods','application/vnd.oasis.opendocument.spreadsheet'),
 (root/'LibreOfficeImpress_odp_1.3.odp','application/vnd.oasis.opendocument.presentation'),
 (root/'testWORD_various.doc','application/msword'),(root/'testEXCEL_macro.xls','application/vnd.ms-excel'),
 (root/'testPPT_various.ppt','application/vnd.ms-powerpoint'),(root/'testRTFUnicodeGothic.rtf','application/rtf'),
 (modern/'sample.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
 (modern/'sample.pptx','application/vnd.openxmlformats-officedocument.presentationml.presentation')]
results=[]
for path,mime in cases:
    start=time.monotonic()
    request=Request(base+'/v1/render',data=path.read_bytes(),headers={'Authorization':'Bearer '+token,'X-Original-Mime':mime})
    try:
        with opener.open(request,timeout=100) as response:
            pdf=response.read(67108865)
            assert pdf.startswith(b'%PDF-') and len(pdf)<=67108864
            result={'name':path.name,'status':response.status,'pdf_bytes':len(pdf),'seconds':round(time.monotonic()-start,2)}
    except HTTPError as exc:result={'name':path.name,'status':exc.code,'error':exc.read(4096).decode()}
    results.append(result);print(json.dumps(result),flush=True)
args.report.write_text(json.dumps(results,indent=2)+'\n')
assert all(item['status']==200 for item in results),results
