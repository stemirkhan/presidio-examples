"""Read saved real runs without new inference or paid calls. Labeled replay."""
from support.runtime import ROOT
import json

print('СОХРАНЕННЫЕ РЕАЛЬНЫЕ ЗАПУСКИ. Новый инференс и API не выполняются.\n')
snapshot=json.loads((ROOT/'evidence/snapshot.json').read_text())
for demo,files in [('D07',['summary.json']),('D08',['summary.json']),('D09',['validation.json']),('D11',['validation.json'])]:
    path=ROOT/snapshot['runs'][demo]
    print(demo,':',path)
    if not path.exists():
        section={'D07':'comparison','D08':'fix','D09':'crewai','D11':'litellm'}[demo]
        print('Локальные сырые файлы отсутствуют. Проверенный снимок:')
        print(json.dumps(snapshot[section],ensure_ascii=False,indent=2));continue
    for file in files:
        if (path/file).exists():print(json.dumps(json.loads((path/file).read_text()),ensure_ascii=False,indent=2))
    print()
