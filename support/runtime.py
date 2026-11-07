"""Local runtime and immutable run records. Never invent predictions."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import shutil
import sys
import traceback
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
for key,value in {
    'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1',
    'HF_HUB_DISABLE_IMPLICIT_TOKEN':'1','TOKENIZERS_PARALLELISM':'false',
    'TLDEXTRACT_PUBLIC_SUFFIX_LIST_URLS':'','TLDEXTRACT_CACHE':str(ROOT/'cache/tld'),
    'OMP_NUM_THREADS':'4','MKL_NUM_THREADS':'4','OPENBLAS_NUM_THREADS':'4',
    'OTEL_SDK_DISABLED':'true','CREWAI_TELEMETRY_ENABLED':'false','CREWAI_TRACING_ENABLED':'false',
    'DO_NOT_TRACK':'1','LITELLM_LOCAL_MODEL_COST_MAP':'true',
}.items(): os.environ[key]=value

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def settings():
    p=ROOT/'local.json'
    return json.loads(p.read_text()) if p.exists() else {}
def local_path(value):
    """Resolve explicit local paths relative to this standalone project."""
    path=Path(value).expanduser()
    return path if path.is_absolute() else ROOT/path
def versions():
    out={}
    for p in ['presidio-analyzer','presidio-anonymizer','spacy','en-core-web-lg','ru-core-news-lg',
              'gliner2','torch','transformers','crewai','litellm','openai','uvicorn','fastapi']:
        try:out[p]=metadata.version(p)
        except metadata.PackageNotFoundError:pass
    return out

class Tee:
    def __init__(self,terminal,file):self.terminal,self.file=terminal,file
    def write(self,s):self.terminal.write(s);self.file.write(s);return len(s)
    def flush(self):self.terminal.flush();self.file.flush()
    def isatty(self):return self.terminal.isatty()

class Run:
    def __init__(self,name,*,step=None,quiet=False):
        self.name=name
        self.quiet=quiet
        parser=argparse.ArgumentParser()
        parser.add_argument('--step',action='store_true')
        parser.add_argument('--check-only',action='store_true',help='Только локальные проверки без платного API')
        args=parser.parse_args() if step is None else argparse.Namespace(step=step,check_only=False)
        self.step=args.step;self.check_only=args.check_only
        stamp=datetime.now(ZoneInfo('Europe/Moscow')).strftime('%Y%m%dT%H%M%S.%f%z')
        self.path=ROOT/'runs'/name/stamp;self.path.mkdir(parents=True)
        self.metadata={'demo':name,'started':datetime.now(ZoneInfo('Europe/Moscow')).isoformat(),
            'python':sys.executable,'versions':versions(),'step':self.step,'check_only':self.check_only,
            'kind':'real_execution','synthetic_input':True,'source_sha256':{}}
        paths=[*ROOT.glob('*.py'),*ROOT.glob('*.yaml'),*ROOT.glob('*.md'),*ROOT.glob('support/*.py'),*ROOT.glob('data/*.json')]
        for p in paths:
            rel=p.relative_to(ROOT);target=self.path/'source'/rel;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(p,target);self.metadata['source_sha256'][str(rel)]=sha(p)
        save(self.path/'metadata.json',self.metadata)
    def __enter__(self):
        self.out=(self.path/'stdout.txt').open('w');self.err=(self.path/'stderr.txt').open('w')
        self.ctxout=redirect_stdout(Tee(sys.stdout,self.out));self.ctxerr=redirect_stderr(Tee(sys.stderr,self.err))
        self.ctxout.__enter__();self.ctxerr.__enter__()
        if not self.quiet:
            print(f'\n{self.name} | Настоящий запуск | Данные вымышлены\n',flush=True)
        return self
    def __exit__(self,typ,exc,tb):
        self.metadata['completed']=exc is None
        if exc is not None:save(self.path/'error.json',{'type':typ.__name__,'message':str(exc),'traceback':''.join(traceback.format_exception(typ,exc,tb))})
        self.metadata['finished']=datetime.now(ZoneInfo('Europe/Moscow')).isoformat();self.save('metadata.json',self.metadata)
        if not self.quiet:
            print('\nАртефакты:',self.path,flush=True)
        self.ctxerr.__exit__(typ,exc,tb);self.ctxout.__exit__(typ,exc,tb);self.err.close();self.out.close()
        (ROOT/f'latest-{self.name}.txt').write_text(str(self.path.relative_to(ROOT))+'\n')
        return False
    def save(self,name,value):save(self.path/name,value)
    def pause(self,label='Enter: продолжить'):
        if self.step:input('\n'+label+' ')
    def show(self,label,value):
        print('\n'+label)
        print(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,indent=2))

def serialize(found,text):
    out=[]
    for r in found:
        item={'entity_type':r.entity_type,'start':r.start,'end':r.end,'score':r.score,'text':text[r.start:r.end],
              'recognizer':(r.recognition_metadata or {}).get('recognizer_name')}
        if r.analysis_explanation:item['explanation']=r.analysis_explanation.to_dict()
        assert 0<=r.start<r.end<=len(text)
        out.append(item)
    return sorted(out,key=lambda r:(r['start'],r['end'],r['entity_type']))

def show_findings(text,found):
    for r in serialize(found,text):print(f"{r['entity_type']:<17} [{r['start']:>3}:{r['end']:<3}] {r['score']:.2f}  {r['text']}")
    if not found:print('Находок нет.')

def model_path(alias):
    models=json.loads((ROOT/'data/models.json').read_text())
    if alias not in models:raise ValueError(f'Неизвестная модель: {alias}')
    configured=settings().get('model_paths',{}).get(alias)
    p=local_path(configured) if configured else ROOT/'models'/alias
    if not p.is_dir():raise RuntimeError(f'Не найдены веса {alias} в {p}; выполните prepare_models.py или укажите model_paths в local.json')
    return p
