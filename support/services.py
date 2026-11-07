"""Start only task-owned local services and stop their exact subprocesses."""
from .runtime import ROOT, save
from contextlib import contextmanager
import json
import os
import subprocess
import time
import urllib.request

def post(url,path,data,timeout=120,headers=None):
    req=urllib.request.Request(url.rstrip('/')+path,data=json.dumps(data,ensure_ascii=False).encode(),headers={'Content-Type':'application/json',**(headers or {})})
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)
def get(url,path,timeout=5):
    with urllib.request.urlopen(url.rstrip('/')+path,timeout=timeout) as r:return json.load(r)

@contextmanager
def privacy_service(run):
    path=run.path/'presidio';path.mkdir()
    with (path/'server.log').open('w') as log:
        command=[str(ROOT/'.venv/bin/python'),'-m','support.privacy_service','--run-dir',str(path)]
        process=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env=os.environ.copy())
        try:
            start=time.monotonic();ready=path/'ready.json'
            while not ready.exists():
                if process.poll() is not None:raise RuntimeError(f'Presidio service stopped; inspect {path}/server.log')
                if time.monotonic()-start>150:raise TimeoutError('Presidio service load timeout')
                time.sleep(.5)
            url=json.loads(ready.read_text())['url'];get(url,'/health');yield url
        finally:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
