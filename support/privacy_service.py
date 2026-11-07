"""Local HTTP adapter around real Presidio. One process = one demo context."""
from .runtime import ROOT, save, serialize
from .detection import make_analyzer, merged, THRESHOLD, inspect_config
from .jwt_recognizer import JwtSessionRecognizer
from .pseudonyms import Vault, TOKEN, mask, restore
from presidio_analyzer import PatternRecognizer, Pattern, RecognizerResult
from presidio_anonymizer import AnonymizerEngine
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import copy
import json
import re
import threading

STRUCTURAL={'id','status','due_at','created_at','as_of','role','depends_on','synthetic','project','task_id','comment_id'}
PROTECTED=re.compile(r'\[[A-Z_]+_\d+_[0-9a-f]{8}\]|\b[A-Z]{2,6}-\d{2,6}\b|\bpay-\d{4}\.\d{2}\.\d{2}\.\d+\b')

class Privacy:
    def __init__(self,path):
        self.path=path;self.lock=threading.RLock();self.counter=0;self.fault=False
        self.analyzer=make_analyzer('metrika');self.vault=Vault();self.cache={}
        self.analyzer.registry.add_recognizer(JwtSessionRecognizer())
        self.analyzer.registry.add_recognizer(PatternRecognizer(name='LoginFormat',supported_entity='USERNAME',supported_language='ru',
            patterns=[Pattern('at_login',r'(?<![\w.])@[A-Za-z0-9_]{3,}',.9)]))
        save(path/'configuration.json',{**inspect_config(self.analyzer,'metrika'),
             'schema_fields_preserved':sorted(STRUCTURAL),'names_forced_by_schema':True,
             'protected_patterns':PROTECTED.pattern,'additional_rules':['JwtSessionRecognizer','LoginFormat'],
             'cache':'Exact text + requested types within this process; model/settings fixed'})
    def analyze(self,text,entities=None):
        key=(text,tuple(sorted(entities or [])))
        if key not in self.cache:
            raw=self.analyzer.analyze(text,language='ru',entities=entities,score_threshold=THRESHOLD)
            protected={i for m in PROTECTED.finditer(text) for i in range(m.start(),m.end())}
            trimmed=[]
            for r in merged(raw):
                start=None
                for i in range(r.start,r.end+1):
                    valid=i<r.end and i not in protected
                    if valid and start is None:start=i
                    if not valid and start is not None:
                        if text[start:i].strip():trimmed.append(RecognizerResult(entity_type=r.entity_type,start=start,end=i,score=r.score))
                        start=None
            self.cache[key]=trimmed
            self.counter+=1;save(self.path/f'analysis-{self.counter:04}.json',{'text':text,'raw':serialize(raw,text),'effective':serialize(trimmed,text)})
        return copy.deepcopy(self.cache[key])
    def text(self,text,forced=None):
        if not text:return text
        if TOKEN.fullmatch(text) and text in self.vault.mapping:return text
        found=[RecognizerResult(entity_type=forced,start=0,end=len(text),score=1)] if forced else self.analyze(text)
        return mask(text,found,self.vault).text
    def tree(self,value,key=None):
        if key in STRUCTURAL:return copy.deepcopy(value)
        if isinstance(value,dict):return {k:self.tree(v,k) for k,v in value.items()}
        if isinstance(value,list):return [self.tree(v,key) for v in value]
        if isinstance(value,str):return self.text(value,'PERSON' if key=='name' else None)
        return value
    def messages(self,messages):
        result=copy.deepcopy(messages)
        for m in result:
            content=m.get('content')
            if isinstance(content,str):
                try:obj=json.loads(content)
                except (ValueError,TypeError):obj=None
                m['content']=json.dumps(self.tree(obj),ensure_ascii=False) if isinstance(obj,(dict,list)) else self.text(content)
            elif isinstance(content,list):
                for part in content:
                    if isinstance(part,dict) and isinstance(part.get('text'),str):part['text']=self.text(part['text'])
            for call in m.get('tool_calls') or []:
                fn=call.get('function',{})
                if isinstance(fn.get('arguments'),str):fn['arguments']=self.text(fn['arguments'])
        return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=0);parser.add_argument('--run-dir',required=True)
    args=parser.parse_args();from pathlib import Path
    path=Path(args.run_dir);path.mkdir(parents=True,exist_ok=True);state=Privacy(path)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,value,status=200):
            b=json.dumps(value,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
        def do_GET(self):
            if self.path=='/health':return self.reply({'status':'ok','backend':'real_presidio_metrika','fault':state.fault})
            if self.path=='/state':return self.reply(state.vault.state())
            self.reply({'error':'not found'},404)
        def do_POST(self):
            try:
                size=int(self.headers.get('Content-Length','0'))
                if size>500000:raise ValueError('Request too large')
                data=json.loads(self.rfile.read(size))
                with state.lock:
                    if self.path=='/fault':state.fault=bool(data['enabled']);return self.reply({'fault':state.fault})
                    if state.fault:raise RuntimeError('Intentional local filter failure')
                    if self.path=='/analyze':
                        found=state.analyze(data['text'],data.get('entities'))
                        return self.reply([{'entity_type':r.entity_type,'start':r.start,'end':r.end,'score':r.score} for r in found])
                    if self.path=='/anonymize':
                        found=[RecognizerResult(entity_type=r['entity_type'],start=r['start'],end=r['end'],score=r.get('score',1)) for r in data['analyzer_results']]
                        result=AnonymizerEngine().anonymize(data['text'],found)
                        state.counter+=1;save(path/f'anonymize-{state.counter:04}.json',{'input':data,'output':result.text})
                        return self.reply({'text':result.text,'items':[r.to_dict() for r in result.items]})
                    if self.path=='/sanitize-tree':return self.reply({'value':state.tree(data['value'])})
                    if self.path=='/sanitize-messages':return self.reply({'messages':state.messages(data['messages'])})
                    if self.path=='/restore':
                        result,details=restore(data['text'],state.vault,allowed_types=data.get('allowed_types',['PERSON','EMAIL_ADDRESS','LOCATION','PHONE_NUMBER','RU_PII','USERNAME','IP_ADDRESS']))
                        return self.reply({'text':result.text,'details':details})
                    self.reply({'error':'not found'},404)
            except Exception as exc:
                self.reply({'error':type(exc).__name__,'message':str(exc)},503)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    save(path/'ready.json',{'port':server.server_port,'url':f'http://127.0.0.1:{server.server_port}'})
    print('Presidio ready on',server.server_port,flush=True)
    server.serve_forever()

if __name__=='__main__':main()
