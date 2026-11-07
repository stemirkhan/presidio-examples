from support.runtime import Run, serialize, show_findings
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import SpacyNlpEngine
from presidio_analyzer.predefined_recognizers import SpacyRecognizer, EmailRecognizer
from presidio_anonymizer import AnonymizerEngine

text = 'Иван Петров подготовит отчет. Его почта: ivan.petrov@example.com.'

with Run('D01') as run:
    nlp = SpacyNlpEngine(models=[{'lang_code':'ru','model_name':'ru_core_news_lg'}])
    registry = RecognizerRegistry(supported_languages=['ru'],recognizers=[
        SpacyRecognizer(supported_language='ru'), EmailRecognizer(supported_language='ru'),
    ])
    analyzer = AnalyzerEngine(nlp_engine=nlp,registry=registry,supported_languages=['ru'])
    run.show('Исходный текст', text)
    run.pause('Enter: выполнить поиск')
    found = analyzer.analyze(text, language='ru', entities=['PERSON', 'EMAIL_ADDRESS'])
    show_findings(text, found)
    run.pause('Enter: заменить найденные фрагменты')
    result = AnonymizerEngine().anonymize(text, found)
    run.show('После замены', result.text)
    run.save('result.json', {'input': text, 'found': serialize(found,text), 'output': result.text})
