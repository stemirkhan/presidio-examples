from support.runtime import Run, serialize
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

text = 'Please contact John Smith at john.smith@example.com.'

with Run('D04') as run:
    found = AnalyzerEngine().analyze(text, language='en', entities=['PERSON','EMAIL_ADDRESS'])
    run.show('Один результат поиска', serialize(found,text))
    variants = {'replace':{}, 'mask':{'masking_char':'*','chars_to_mask':100,'from_end':False}, 'redact':{}}
    outputs = {}
    for operation, params in variants.items():
        run.pause('Enter: '+operation)
        result = AnonymizerEngine().anonymize(text,found,operators={'DEFAULT':OperatorConfig(operation,params)})
        outputs[operation] = result.text
        run.show(operation,result.text)
    run.save('result.json', {'input':text,'found':serialize(found,text),'outputs':outputs})
