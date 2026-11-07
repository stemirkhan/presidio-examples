from support.runtime import Run, serialize, show_findings
from support.detection import make_analyzer, customer_rule, THRESHOLD

text = 'Клиент Марина Соколова, почта marina.sokolova@example.com. Внутренний ID CUST-4821.'

with Run('D02') as run:
    analyzer = make_analyzer('baseline')
    selected = analyzer.registry.get_recognizers(language='ru', entities=['EMAIL_ADDRESS'])
    run.show('Для EMAIL_ADDRESS выбраны', [r.name for r in selected])
    email = analyzer.analyze(text, language='ru', entities=['EMAIL_ADDRESS'], score_threshold=THRESHOLD)
    show_findings(text, email)
    run.pause('Enter: добавить распознаватель внутреннего ID')
    before = analyzer.analyze(text, language='ru', score_threshold=THRESHOLD)
    analyzer.registry.add_recognizer(customer_rule())
    after = analyzer.analyze(text, language='ru', score_threshold=THRESHOLD)
    run.show('После регистрации правила', text)
    show_findings(text, after)
    run.save('result.json', {'text':text,'email_only':serialize(email,text),'before':serialize(before,text),'after':serialize(after,text)})
