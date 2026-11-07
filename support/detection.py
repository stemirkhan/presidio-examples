"""Three explicitly configured Presidio pipelines with a common output policy."""
from .runtime import ROOT, model_path
import gc
import json
from presidio_analyzer import AnalyzerEngine, LocalRecognizer, Pattern, PatternRecognizer, RecognizerRegistry, RecognizerResult
from presidio_analyzer.nlp_engine import SpacyNlpEngine, NerModelConfiguration
from presidio_analyzer.predefined_recognizers import EmailRecognizer, PhoneRecognizer, IpRecognizer, DateRecognizer, SpacyRecognizer
from presidio_anonymizer import AnonymizerEngine

THRESHOLD=0.5
SPECS=json.loads((ROOT/'data/models.json').read_text())

class Gliner25Recognizer(LocalRecognizer):
    def __init__(self,alias):
        self.alias=alias;self.spec=SPECS[alias];self.labels=self.spec['labels'];self.raw=None
        super().__init__(supported_entities=sorted(set(self.labels.values())),supported_language='ru',name=f'{alias}_GLiNER25')
    def load(self):
        import torch
        from gliner2 import AutoExtractor
        torch.set_num_threads(4)
        try:torch.set_num_interop_threads(1)
        except RuntimeError:pass
        torch.manual_seed(42)
        self.model=AutoExtractor.from_pretrained(str(model_path(self.alias)),map_location='cpu')
        self.model.eval()
    def analyze(self,text,entities,nlp_artifacts=None):
        import torch
        with torch.inference_mode():
            self.raw=self.model.extract_entities(text,list(self.labels),threshold=THRESHOLD,include_spans=True,include_confidence=True)
        results=[]
        for label,values in self.raw['entities'].items():
            for v in values:
                kind=self.labels[label]
                if entities and kind not in entities:continue
                start,end=v['start'],v['end']
                assert text[start:end]==v['text'], 'Model offsets do not refer to original text'
                results.append(RecognizerResult(entity_type=kind,start=start,end=end,score=float(v['confidence']),
                    recognition_metadata={'recognizer_name':self.name,'recognizer_identifier':self.id}))
        return results

def common_rules():
    return [EmailRecognizer(supported_language='ru'),
            PhoneRecognizer(supported_language='ru',supported_regions=['RU','KZ'],context=['телефон','мобильный','позвонить','контакт']),
            IpRecognizer(supported_language='ru'),DateRecognizer(supported_language='ru')]

def russian_nlp():
    return SpacyNlpEngine(models=[{'lang_code':'ru','model_name':'ru_core_news_lg'}],
        ner_model_configuration=NerModelConfiguration(labels_to_ignore=['ORG','ORGANIZATION']))

def make_analyzer(config='baseline'):
    nlp=russian_nlp()
    registry=RecognizerRegistry(supported_languages=['ru'],recognizers=common_rules())
    if config=='baseline':registry.add_recognizer(SpacyRecognizer(supported_language='ru',supported_entities=['PERSON','LOCATION','DATE_TIME']))
    else:registry.add_recognizer(Gliner25Recognizer(config))
    engine=AnalyzerEngine(registry=registry,nlp_engine=nlp,supported_languages=['ru'])
    names=[r.name for r in engine.registry.recognizers]
    if config!='baseline':assert not any(isinstance(r,SpacyRecognizer) for r in engine.registry.recognizers)
    return engine

def customer_rule():
    return PatternRecognizer(name='InternalCustomerId',supported_entity='CUSTOMER_ID',supported_language='ru',
        patterns=[Pattern(name='CUST plus four digits',regex=r'\bCUST-\d{4}\b',score=.95)])

def merged(found):
    """Keep the union, select an exact specific label where possible. No span loss."""
    clusters=[]
    for r in sorted(found,key=lambda r:(r.start,r.end,r.entity_type)):
        if clusters and r.start<clusters[-1]['end']:
            clusters[-1]['end']=max(clusters[-1]['end'],r.end);clusters[-1]['items'].append(r)
        else:clusters.append({'start':r.start,'end':r.end,'items':[r]})
    out=[]
    for c in clusters:
        exact=[r for r in c['items'] if r.start==c['start'] and r.end==c['end']]
        if exact:
            r=min(exact,key=lambda r:(r.entity_type=='RU_PII',r.entity_type,-r.score));kind,score=r.entity_type,r.score
        else:kind,score='RU_PII',max(r.score for r in c['items'])
        out.append(RecognizerResult(entity_type=kind,start=c['start'],end=c['end'],score=score))
    return out

def anonymize(text,found):return AnonymizerEngine().anonymize(text=text,analyzer_results=merged(found))

def inspect_config(engine,alias):
    return {'alias':alias,'nlp':'ru_core_news_lg 3.8.0','language':'ru','analyzer_threshold':THRESHOLD,
        'model':SPECS.get(alias),'recognizers':[r.name for r in engine.registry.recognizers],
        'shared_phone_regions':['RU','KZ'],'shared_phone_context':['телефон','мобильный','позвонить','контакт'],
        'dtype':'float32','device':'cpu','batch_size':1,'threads':4,'spacy_ner_participates':alias=='baseline'}

def neural_raw(engine):
    r=next((r for r in engine.registry.recognizers if isinstance(r,Gliner25Recognizer)),None)
    return r.raw if r else None
