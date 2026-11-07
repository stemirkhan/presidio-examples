"""Explicit local mapping and real Presidio operators in both directions."""
from .runtime import ROOT
from collections import defaultdict
import re
import uuid
from presidio_anonymizer import AnonymizerEngine, DeanonymizeEngine
from presidio_anonymizer.entities import OperatorConfig, OperatorResult
from presidio_anonymizer.operators import Operator, OperatorType

TOKEN=re.compile(r'\[[A-Z_]+_\d+_[0-9a-f]{8}\]')

class Vault:
    def __init__(self):self.nonce=uuid.uuid4().hex[:8];self.by_value={};self.mapping={};self.types={};self.counts=defaultdict(int)
    def issue(self,kind,value):
        key=(kind,value)
        if key not in self.by_value:
            self.counts[kind]+=1;token=f'[{kind}_{self.counts[kind]}_{self.nonce}]'
            self.by_value[key]=token;self.mapping[token]=value;self.types[token]=kind
        return self.by_value[key]
    def state(self):return {'nonce':self.nonce,'mapping':self.mapping,'types':self.types}

class SessionTokenOperator(Operator):
    def operate(self,text,params=None):return params['vault'].issue(params['entity_type'],text)
    def validate(self,params=None):
        if not isinstance((params or {}).get('vault'),Vault):raise ValueError('Local Vault is required')
    def operator_name(self):return 'session_token'
    def operator_type(self):return OperatorType.Anonymize

class RestoreOperator(Operator):
    def operate(self,text,params=None):
        vault=params['vault']
        if vault.types.get(text) not in params['allowed_types']:return text
        return vault.mapping.get(text,text)
    def validate(self,params=None):
        if not isinstance((params or {}).get('vault'),Vault):raise ValueError('Local Vault is required')
        if 'allowed_types' not in params:raise ValueError('Explicit allowed types required')
    def operator_name(self):return 'restore_from_map'
    def operator_type(self):return OperatorType.Deanonymize

def mask(text,found,vault):
    engine=AnonymizerEngine();engine.add_anonymizer(SessionTokenOperator)
    return engine.anonymize(text,found,operators={'DEFAULT':OperatorConfig('session_token',{'vault':vault})})

def restore(text,vault,allowed_types=('PERSON','EMAIL_ADDRESS','LOCATION','RU_PII','PHONE_NUMBER')):
    entities=[];unknown=[];withheld=[]
    for m in TOKEN.finditer(text):
        tag=m.group(0);kind=vault.types.get(tag)
        if kind is None:unknown.append(tag);continue
        if kind not in allowed_types:withheld.append(tag);continue
        entities.append(OperatorResult(start=m.start(),end=m.end(),entity_type=kind,text=tag,operator='restore_from_map'))
    engine=DeanonymizeEngine();engine.add_deanonymizer(RestoreOperator)
    out=engine.deanonymize(text,entities,operators={'DEFAULT':OperatorConfig('restore_from_map',{'vault':vault,'allowed_types':allowed_types})})
    return out,{'current_response_spans':[r.to_dict() for r in entities],'unknown':sorted(set(unknown)),'withheld':sorted(set(withheld))}
