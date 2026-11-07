from .runtime import ROOT
from .services import get
from contextlib import contextmanager
import os
import socket
import secrets
import subprocess
import time

@contextmanager
def proxy_service(run,presidio,gateway):
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env=os.environ.copy();env.update({'PRESIDIO_ANALYZER_API_BASE':presidio,'PRESIDIO_ANONYMIZER_API_BASE':presidio,
        'DEMO_GATEWAY_BASE':gateway.url,'LITELLM_LOCAL_MODEL_COST_MAP':'true','NO_COLOR':'1'})
    # Short-lived local proxy authentication; never serialized.
    local_key='sk-'+secrets.token_hex(32);env['LITELLM_MASTER_KEY']=local_key
    command=[str(ROOT/'.venv-proxy/bin/litellm'),'--config',str(ROOT/'litellm.yaml'),'--host','127.0.0.1','--port',str(port)]
    with (run.path/'litellm.log').open('w') as log:
        process=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env=env)
        try:
            url=f'http://127.0.0.1:{port}';start=time.monotonic()
            while True:
                if process.poll() is not None:raise RuntimeError('LiteLLM stopped; inspect litellm.log')
                try:get(url,'/health/liveliness');break
                except Exception:
                    if time.monotonic()-start>75:raise TimeoutError('LiteLLM startup timeout')
                    time.sleep(.5)
            yield url,{'Authorization':'Bearer '+local_key}
        finally:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
