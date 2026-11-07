from support.runtime import Run, ROOT, serialize
from support.detection import make_analyzer, anonymize
from support.comparison import evaluate, cases
from support.jwt_recognizer import JwtSessionRecognizer
import json

with Run('D08') as run:
    cases()  # verify the frozen control data before inference
    tracker = json.loads((ROOT/'data/tracker.json').read_text())
    text = next(t for t in tracker['tasks'] if t['id']=='SEC-243')['comments'][0]['body']
    analyzer = make_analyzer('metrika')
    before = analyzer.analyze(text,language='ru',score_threshold=.5)
    run.show('До добавления правила; известный случай из прежнего опыта',anonymize(text,before).text)
    run.pause('Enter: добавить распознаватель JWT-формата')
    analyzer.registry.add_recognizer(JwtSessionRecognizer())
    after = analyzer.analyze(text,language='ru',score_threshold=.5)
    run.show('После добавления правила',anonymize(text,after).text)
    run.save('development.json',{'input':text,'before':serialize(before,text),'after':serialize(after,text)})

    controls = json.loads((ROOT/'data/fix-checks.json').read_text())
    rows=[]
    for case in controls['positive']+controls['negative']:
        found = analyzer.analyze(case['text'],language='ru',score_threshold=.5)
        jwt = [r for r in found if r.entity_type=='ACCESS_TOKEN']
        row={'id':case['id'],'text':case['text'],'found':serialize(found,case['text']),
             'jwt_matches':len(jwt),'any_redaction':bool(found)}
        if 'token' in case:
            start=case['text'].index(case['token']);end=start+len(case['token'])
            row['token_fully_covered']=any(r.start<=start and r.end>=end for r in jwt)
        rows.append(row);run.save(case['id']+'.json',row)
    summary={'new_tokens':len(controls['positive']),'tokens_fully_covered':sum(r.get('token_fully_covered',False) for r in rows),
             'negatives':len(controls['negative']),'negative_jwt_matches':sum(r['jwt_matches']>0 for r in rows if r['id'].startswith('negative')),
             'negative_any_redaction':sum(r['any_redaction'] for r in rows if r['id'].startswith('negative')),
             'training_performed':False}
    run.show('Контроль выбранного формата, не всех возможных секретов',summary)
    run.save('summary.json',summary)
