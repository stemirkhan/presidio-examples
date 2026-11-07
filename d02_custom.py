from support.runtime import Run, serialize, show_findings
from support.detection import make_analyzer, THRESHOLD
from presidio_analyzer import Pattern, PatternRecognizer

text = (
    "Иван Петров подготовит отчет. Его почта: ivan.petrov@example.com. "
    "Номер клиента: CUST-4821."
)

with Run("D02-custom", quiet=True) as run:
    analyzer = make_analyzer("baseline")
    before = analyzer.analyze(text=text, language="ru", score_threshold=THRESHOLD)
    run.show("ДО ДОБАВЛЕНИЯ ПРАВИЛА", "")
    show_findings(text, before)

    customer_id = PatternRecognizer(
        name="InternalCustomerId", supported_entity="CUSTOMER_ID", supported_language="ru",
        patterns=[Pattern(name="CUST и четыре цифры", regex=r"\bCUST-[0-9]{4}\b", score=0.95)],
    )
    analyzer.registry.add_recognizer(customer_id)

    after = analyzer.analyze(text=text, language="ru", score_threshold=THRESHOLD)
    run.show("ПОСЛЕ ДОБАВЛЕНИЯ ПРАВИЛА", "")
    show_findings(text, after)
    run.save("result.json", {
        "text": text, "language": "ru", "entities": None, "threshold": THRESHOLD,
        "pattern": customer_id.patterns[0].regex, "pattern_score": 0.95,
        "before": serialize(before, text), "after": serialize(after, text),
    })
