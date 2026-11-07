"""Read-only preparation check; does not load model weights or call APIs."""
from pathlib import Path
import json
import subprocess
import xml.etree.ElementTree as ET

from support.runtime import ROOT, local_path, model_path, settings


def main():
    root=ROOT
    checks=[]
    for env,modules in [('.venv',['presidio_analyzer','presidio_anonymizer','spacy','en_core_web_lg','ru_core_news_lg','gliner2','torch']),
                        ('.venv-agent',['crewai','openai']),('.venv-proxy',['litellm','fastapi'])]:
        py=root/env/'bin/python'
        if not py.exists():
            checks.append({'environment':env,'ok':False,'missing':'interpreter','action':'Run python3.12 setup_environments.py'})
            continue
        code=('import importlib.util,json,sys; print(json.dumps({"python":list(sys.version_info[:2]),"modules":'
              '{m: importlib.util.find_spec(m) is not None for m in '+repr(modules)+'}}))')
        try:
            result=subprocess.run([str(py),'-c',code],text=True,capture_output=True,timeout=30)
            available=json.loads(result.stdout) if result.returncode==0 else {}
            ok=available.get('python')==[3,12] and all(available.get('modules',{}).values())
            checks.append({'environment':env,'ok':ok,**available})
        except (OSError,subprocess.TimeoutExpired,json.JSONDecodeError) as exc:
            checks.append({'environment':env,'ok':False,'error':str(exc)})
    try:
        local=settings()
        settings_ok=True
    except (OSError,ValueError) as exc:
        local={};settings_ok=False
        checks.append({'local_settings':'local.json','ok':False,'error':str(exc)})
    for alias in ['fastino','metrika']:
        try:
            model=model_path(alias)
            missing=[name for name in ['model.safetensors','tokenizer.json'] if not (model/name).is_file()]
            checks.append({'model':alias,'ok':not missing,'missing':missing})
        except (OSError,ValueError,RuntimeError) as exc:
            checks.append({'model':alias,'ok':False,'error':str(exc)})
    configs=sorted((root/'.run').glob('*.xml'))
    invalid=[];missing=[]
    for file in configs:
        try:
            configuration=ET.parse(file).getroot().find('configuration')
            if configuration is None:raise ValueError('No configuration element')
            options={x.get('name'):x.get('value','') for x in configuration.findall('option')}
            for key in ['SDK_HOME','SCRIPT_NAME','WORKING_DIRECTORY']:
                value=options.get(key,'')
                if not (value=='$PROJECT_DIR$' or value.startswith('$PROJECT_DIR$/')):
                    invalid.append({'configuration':file.name,'option':key,'reason':'Path must use $PROJECT_DIR$'})
                elif not Path(value.replace('$PROJECT_DIR$',str(root))).exists():
                    missing.append({'configuration':file.name,'option':key})
        except (OSError,ET.ParseError,ValueError) as exc:
            invalid.append({'configuration':file.name,'error':str(exc)})
    checks.append({'run_configurations':len(configs),'ok':len(configs)==29 and not invalid and not missing,
                   'invalid':invalid,'missing_paths':missing})
    budget={'optional_for_offline':True,'present':False,'has_capacity':False}
    if settings_ok:
        try:
            budget_path=local_path(local.get('budget_file','api-budget.json'))
            budget['present']=budget_path.is_file()
            if budget['present']:
                ledger=json.loads(budget_path.read_text())
                approved=float(ledger['approved_usd']);reserved=float(ledger['reserved_upper_usd'])
                budget['has_capacity']=approved>0 and 0<=reserved<approved
        except (OSError,ValueError,KeyError,TypeError) as exc:
            budget['error']=str(exc)
    offline_ready=all(x['ok'] for x in checks)
    print(json.dumps({'checks':checks,'run_configurations':len(configs),'budget':budget,'api_called':False,
                      'ready':offline_ready,'offline_ready':offline_ready,
                      'paid_ready':offline_ready and budget['has_capacity'],
                      'note':'An approved budget ledger is required only for paid D09/D11 runs. API credentials are not checked.'},
                     ensure_ascii=False,indent=2))
    if not offline_ready:raise SystemExit(1)


if __name__=='__main__':main()
