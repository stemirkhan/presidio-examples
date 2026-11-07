from support.runtime import Run, serialize
from support.detection import make_analyzer

text = 'Передайте документы Марине Соколовой в Твери.'

with Run('D03') as run:
    analyzer = make_analyzer('baseline')
    artifacts = analyzer.nlp_engine.process_text(text, language='ru')
    words = [{'text':t.text, 'start':t.idx, 'lemma':t.lemma_} for t in artifacts.tokens]
    run.show('Реальные токены, позиции и начальные формы', words)
    run.pause('Enter: передать готовый разбор распознавателям')
    found = analyzer.analyze(text, language='ru', nlp_artifacts=artifacts, score_threshold=.5)
    run.show('Сущности', serialize(found, text))
    run.save('result.json', {'text':text,'tokens':words,'found':serialize(found,text)})
