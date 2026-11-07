from support.runtime import Run, serialize, show_findings
from support.detection import make_analyzer, anonymize, inspect_config, neural_raw
import gc

text = 'Куратор Александр Романов, почта curator.demo@example.org.'

with Run('D06') as run:
    for model in ['fastino','metrika']:
        analyzer = make_analyzer(model)
        run.show('Подключенная модель',inspect_config(analyzer,model))
        found = analyzer.analyze(text,language='ru',score_threshold=.5)
        show_findings(text,found)
        output = anonymize(text,found).text
        run.show('После обработки',output)
        run.save(model+'.json',{'text':text,'found':serialize(found,text),'raw_model':neural_raw(analyzer),'output':output})
        del analyzer
        gc.collect()
        run.pause('Enter: продолжить')
