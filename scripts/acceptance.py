"""Run isolated real acceptance suites in order; reports live outside the checkout.

Source-browser Docker fixtures run before other Chromium suites to avoid network
interface changes during browser navigation. Never resets or restores the normal
Compose data volume, modifies credentials, pushes Git or installs dependencies.
"""
import argparse
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]


def summarize(path):
    cases=ET.parse(path).findall('.//testcase')
    counts={'total':len(cases),'passed':0,'failed':0,'skipped':0}
    for case in cases:
        if case.find('failure') is not None or case.find('error') is not None:counts['failed']+=1
        elif case.find('skipped') is not None:counts['skipped']+=1
        else:counts['passed']+=1
    return counts


def case_map():
    cases=json.loads((ROOT/'scripts/acceptance-cases.json').read_text())
    expected={f'UX-{i:02}' for i in range(1,15)}|{f'META-{i:02}' for i in range(1,17)}
    if len(cases)!=30 or {case['id'] for case in cases}!=expected:raise ValueError('Incomplete acceptance registry')
    for case in cases:
        for node in case['python']:
            file,name=node.split('::')
            functions={n.name for n in ast.parse((ROOT/file).read_text()).body if isinstance(n,ast.FunctionDef)}
            if name not in functions:raise ValueError('Acceptance test missing: '+node)
    return cases


def assess(cases, directories):
    backend={};browser={}
    for directory in directories:
        path=directory/'backend.xml'
        if path.exists():
            for case in ET.parse(path).findall('.//testcase'):
                node=case.attrib['classname'].replace('.','/')+'.py::'+case.attrib['name'].split('[')[0]
                state='failed' if case.find('failure') is not None or case.find('error') is not None else 'not_run' if case.find('skipped') is not None else 'passed'
                backend.setdefault(node,[]).append(state)
        for name in ('sources','library','reading','search','jobs','files'):
            path=directory/(name+'.xml')
            if path.exists():
                count=summarize(path)
                browser.setdefault(name,[]).append('failed' if count['failed'] else 'not_run' if not count['total'] or count['skipped'] else 'passed')
    results=[]
    for case in cases:
        states=[state for node in case['python'] for state in backend.get(node,['not_run'])]
        states += [state for name in case['browser_suites'] for state in browser.get(name,['not_run'])]
        results.append({'id':case['id'],'status':'failed' if 'failed' in states else 'not_run' if 'not_run' in states else 'passed'})
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=('all','backend','browser','assess'),default='all')
    parser.add_argument('--output',type=Path,help='New report directory outside repository; default private /tmp directory')
    parser.add_argument("--reports",type=Path,nargs="+",help="Existing current-run backend/browser report directories for assess")
    args=parser.parse_args()
    cases=case_map()
    if args.phase=="assess" and not args.reports:parser.error("assess requires explicit report directories")
    if args.output:
        output=args.output.resolve()
        if output.is_relative_to(ROOT):parser.error('Reports must be outside repository')
        output.mkdir(mode=0o700)
    else:output=Path(tempfile.mkdtemp(prefix='juanzhan-acceptance-'))
    env=dict(os.environ)
    env.setdefault('UV_CACHE_DIR',str(ROOT/'.local/uv-cache'))
    env.setdefault('DOCKER_CONFIG',str(ROOT/'.local/docker'))
    if not env.get('JUANZHAN_CHROMIUM_PATH') and shutil.which('chromium'):
        env['JUANZHAN_CHROMIUM_PATH']=shutil.which('chromium')
    if args.phase=='assess':
        results=assess(cases,args.reports)
        passed=all(case['status']=='passed' for case in results)
        report={'phase':'assess','status':'passed' if passed else 'failed','reports':[str(p) for p in args.reports],
                'acceptance_cases':results}
        (output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(str(sum(case['status']=='passed' for case in results))+'/30 acceptance cases passed; '+str(output/'summary.json'))
        raise SystemExit(0 if passed else 1)
    steps=[]
    if args.phase in ('all','backend'):
        steps.append(('backend',ROOT,['uv','run','--frozen','pytest','-q','--junitxml='+str(output/'backend.xml')],output/'backend.xml'))
    if args.phase in ('all','browser'):
        steps.append(('web-build',ROOT/'web',['npm','run','build'],None))
        for name,script in [('sources','test:e2e:sources'),('library','test:e2e'),('reading','test:e2e:reading'),
                            ('search','test:e2e:search'),('jobs','test:e2e:jobs'),('files','test:e2e:files')]:
            steps.append((name,ROOT/'web',['npm','run',script,'--','--reporter=list,junit'],output/(name+'.xml')))
    report={'phase':args.phase,'started_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
            'browser':'Browser plugin not available; existing Playwright/Chromium',
            'steps':[],'status':'running'}
    report_path=output/'summary.json'
    code=0
    for name,cwd,command,result in steps:
        step_env=dict(env)
        if result and name!='backend':step_env['PLAYWRIGHT_JUNIT_OUTPUT_FILE']=str(result)
        print('Running '+name,flush=True)
        start=time.monotonic()
        child=subprocess.run(command,cwd=cwd,env=step_env)
        step={'name':name,'exit_code':child.returncode,'seconds':round(time.monotonic()-start,2)}
        if result:
            try:
                step['tests']=summarize(result)
                if step['tests']['total']==0 or step['tests']['skipped'] or step['tests']['failed']:code=1
            except (OSError,ET.ParseError):step['report_error']='Missing or invalid test report';code=1
        report['steps'].append(step)
        if child.returncode:code=child.returncode if child.returncode>0 else 1
        report['status']='failed' if code else 'running'
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        if code:break  # Keep the first failure; absent later phases remain unrun.
    report['acceptance_cases']=assess(cases,[output])
    if args.phase=='all' and any(case['status']!='passed' for case in report['acceptance_cases']):code=1
    report['status']='failed' if code else 'passed'
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('Acceptance '+report['status']+'; report: '+str(report_path),flush=True)
    raise SystemExit(code)

if __name__=='__main__':main()
