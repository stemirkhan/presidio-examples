from support.runtime import Run
from support.comparison import compare

with Run('D05') as run:
    run.show('Конфигурация', 'Стандартные распознаватели + явно настроенная ru_core_news_lg')
    result = compare(run, ['baseline'])
    run.show('Итог фиксированного набора',result)
