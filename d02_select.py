from support.runtime import Run, serialize, show_findings
from support.detection import make_analyzer, THRESHOLD

text = (
    "Иван Петров подготовит отчет. Его почта: ivan.petrov@example.com. "
    "Номер клиента: CUST-4821."
)

with Run("D02-select", quiet=True) as run:
    analyzer = make_analyzer("baseline")
    entities = ["EMAIL_ADDRESS"]
    selected = analyzer.registry.get_recognizers(language="ru", entities=entities)

    run.show("ИСХОДНЫЙ ТЕКСТ", text)
    run.show("ВЫБРАНЫ РАСПОЗНАВАТЕЛИ", sorted(r.name for r in selected))
    found = analyzer.analyze(
        text=text, language="ru", entities=entities, score_threshold=THRESHOLD,
    )
    run.show("РЕЗУЛЬТАТ ПОИСКА", "")
    show_findings(text, found)
    run.save("result.json", {
        "text": text, "language": "ru", "entities": entities,
        "selected": sorted(r.name for r in selected), "found": serialize(found, text),
    })
