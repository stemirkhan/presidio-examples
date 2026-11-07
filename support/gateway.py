"""Diagnostic egress gateway: real upstream calls, per-call audit and shared budget."""
from .runtime import ROOT, save, settings
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import copy
import fcntl
import getpass
import json
import math
import os
import sys
import tempfile
import threading
import urllib.request
import urllib.error

MODEL='deepseek-flash'
RATES={'input_peak_per_million':.30,'output_peak_per_million':1.20}
MAX_BUDGET_USD=3.0

def budget_path(override=None):
    """Use the viewer's project ledger, or an explicitly shared ledger."""
    configured=override if override is not None else settings().get('budget_file',ROOT/'api-budget.json')
    if not isinstance(configured,(str,os.PathLike)) or not str(configured).strip():
        raise ValueError('budget_file must be a nonempty path')
    path=Path(configured).expanduser()
    return (path if path.is_absolute() else ROOT/path).resolve()

def finite_amount(value,label):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
        raise ValueError(f'{label} must be a finite nonnegative number')
    return float(value)

def validate_limit(value):
    limit=finite_amount(value,'approved_usd')
    if limit>MAX_BUDGET_USD:raise ValueError(f'Limit must be between 0 and ${MAX_BUDGET_USD:g}')
    return limit

def write_ledger(path,ledger):
    """Replace the ledger atomically while its separate .lock is held."""
    temporary=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,prefix=path.name+'.',suffix='.tmp',delete=False) as file:
            temporary=Path(file.name)
            json.dump(ledger,file,ensure_ascii=False,indent=2);file.write('\n');file.flush();os.fsync(file.fileno())
        os.replace(temporary,path)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)

def read_key():
    key=os.environ.get('DEEPSEEK_API_KEY','').strip()
    if not key:
        if not sys.stdin.isatty():raise RuntimeError('Задайте DEEPSEEK_API_KEY до записи или включите Emulate terminal в PyCharm; ключ не выводится и не сохраняется.')
        key=getpass.getpass('DeepSeek API key (ввод скрыт, не сохраняется): ').strip()
    if not key:raise RuntimeError('API key is empty')
    return key

class Gateway:
    def __init__(self,path,key,forbidden=(),max_calls=12):
        path=Path(path)
        self.path=path;self.key=key;self.forbidden=list(forbidden);self.max_calls=max_calls
        self.received=0;self.forwarded=0;self.responses=[];self.lock=threading.Lock()
        self.ledger_path=budget_path()
        # Failure checks have no provider key and cannot reach the network.
        # Do not create or reset a spending budget for an offline check.
        if key and not self.ledger_path.is_file():
            raise RuntimeError('Budget ledger is missing; run init_budget.py --limit-usd 3 (or a smaller limit) first')
        self.ledger_lock=self.ledger_path.with_suffix('.lock')
        gateway=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def reply(self,value,status=200):
                b=json.dumps(value,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
            def do_GET(self):
                if self.path in ['/health','/v1/models','/models']:
                    return self.reply({'object':'list','data':[{'id':MODEL,'object':'model'}]})
                self.reply({'error':'not found'},404)
            def do_POST(self):
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if size>250000:raise RuntimeError('Request exceeds demo bound')
                    payload=json.loads(self.rfile.read(size))
                    with gateway.lock:
                        gateway.received+=1;seq=gateway.received
                        raw=json.dumps(payload,ensure_ascii=False)
                        leaks=[v for v in gateway.forbidden if v in raw]
                        save(path/f'{seq:02d}-received.json',payload)
                        if leaks:
                            save(path/f'{seq:02d}-blocked.json',{'reason':'Known original fixture values remain','count':len(leaks)})
                            return self.reply({'error':{'message':'Local egress check blocked unmasked fixture data'}},422)
                        if not gateway.key:return self.reply({'error':{'message':'Network disabled in failure test'}},503)
                        if gateway.forwarded>=gateway.max_calls:raise RuntimeError('Maximum API calls for this demonstration reached')
                        # Protocol-only normalization; messages and tools are not rewritten here.
                        body=copy.deepcopy(payload);body['model']=MODEL;body['stream']=False
                        body['thinking']={'type':'disabled'};body['max_tokens']=min(int(body.pop('max_completion_tokens',body.get('max_tokens',4096))),4096)
                        for k in ['metadata','store','reasoning_effort']:body.pop(k,None)
                        encoded=json.dumps(body,ensure_ascii=False).encode()
                        reservation=((len(encoded)+8192)*RATES['input_peak_per_million']+body['max_tokens']*RATES['output_peak_per_million'])/1e6
                        call_id=f'{path.parent.name}:{path.name}:{seq}'
                        gateway.update_budget(call_id,reservation=reservation)
                        save(path/f'{seq:02d}-upstream-request.json',body);gateway.forwarded+=1
                        request=urllib.request.Request('https://api.deepseek.com/chat/completions',data=encoded,
                            headers={'Authorization':'Bearer '+gateway.key,'Content-Type':'application/json'})
                        try:
                            with urllib.request.urlopen(request,timeout=150) as response:answer=json.load(response)
                        except urllib.error.HTTPError as exc:
                            details=exc.read().decode(errors='replace').replace(gateway.key,'[REDACTED]')
                            save(path/f'{seq:02d}-provider-error.json',{'status':exc.code,'body':details})
                            gateway.update_budget(call_id,status='failed')
                            return self.reply({'error':{'message':details}},exc.code)
                        except (urllib.error.URLError,TimeoutError) as exc:
                            message=str(exc).replace(gateway.key,'[REDACTED]')
                            save(path/f'{seq:02d}-transport-error.json',{'type':type(exc).__name__,'message':message})
                            gateway.update_budget(call_id,status='transport_failed')
                            return self.reply({'error':{'message':message}},502)
                        save(path/f'{seq:02d}-response.json',answer);gateway.responses.append(answer)
                        gateway.update_budget(call_id,usage=answer.get('usage',{}),status='completed')
                        print(f'DeepSeek: вызов {gateway.forwarded}, исходящие данные проверены',flush=True)
                        return self.reply(answer)
                except Exception as exc:
                    message=str(exc).replace(gateway.key,'[REDACTED]') if gateway.key else str(exc)
                    self.reply({'error':{'message':message}},500)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.url=f'http://127.0.0.1:{self.server.server_port}/v1'
    def update_budget(self,call_id,reservation=None,usage=None,status=None):
        if not self.ledger_path.is_file():raise RuntimeError('Initialized budget ledger is required before a provider call')
        self.ledger_lock.parent.mkdir(parents=True,exist_ok=True)
        with self.ledger_lock.open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            ledger=json.loads(self.ledger_path.read_text())
            approved=validate_limit(ledger['approved_usd'])
            reserved=finite_amount(ledger['reserved_upper_usd'],'reserved_upper_usd')
            estimated=finite_amount(ledger['usage_estimate_upper_usd'],'usage_estimate_upper_usd')
            if reserved>approved:raise RuntimeError('Budget ledger already exceeds its approved reservation limit')
            if not isinstance(ledger['calls'],list):raise ValueError('Budget ledger calls must be a list')
            if reservation is not None:
                reservation=finite_amount(reservation,'reservation')
                if reservation==0:raise ValueError('Reservation must be positive')
                if any(c.get('call_id')==call_id for c in ledger['calls']):raise RuntimeError('Call is already reserved')
                if max(reserved,estimated)+reservation>approved:raise RuntimeError(f'Approved ${approved:g} budget exhausted')
                ledger['reserved_upper_usd']=reserved+reservation
                ledger['calls'].append({'call_id':call_id,'run':str(self.path),'status':'reserved','reserved_upper_usd':reservation,'rates':RATES})
            else:
                entry=next(c for c in ledger['calls'] if c.get('call_id')==call_id)
                if entry['status']!='reserved':raise RuntimeError('Call is already settled')
                if status not in {'completed','failed','transport_failed'}:raise ValueError('Unknown settlement status')
                if usage:
                    prompt=finite_amount(usage.get('prompt_tokens',0),'prompt_tokens')
                    completion=finite_amount(usage.get('completion_tokens',0),'completion_tokens')
                    estimate=(prompt*RATES['input_peak_per_million']+completion*RATES['output_peak_per_million'])/1e6
                    entry.update({'usage':usage,'usage_estimate_upper_usd':estimate});ledger['usage_estimate_upper_usd']+=estimate
                entry['status']=status
            # Reservations remain charged after success or uncertain failures.
            write_ledger(self.ledger_path,ledger)
    def __enter__(self):
        self.path.mkdir(parents=True,exist_ok=True)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();return self
    def __exit__(self,*args):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)
        save(self.path/'summary.json',{'received':self.received,'forwarded':self.forwarded,'responses':len(self.responses),
             'model':MODEL,'budget_file':str(self.ledger_path),'api_key_saved':False})
        self.key=''
