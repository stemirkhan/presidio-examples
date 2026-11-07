from support.runtime import Run
from support.comparison import compare

with Run('D07') as run:
    run.show('Условия', '20 зафиксированных текстов, три конфигурации, одинаковые общие правила и оператор')
    result = compare(run,['baseline','fastino','metrika'])
    run.show('Фактические итоги',result)
