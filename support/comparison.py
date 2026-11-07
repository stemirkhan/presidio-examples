from .runtime import ROOT, sha, serialize, save
from .detection import THRESHOLD, make_analyzer, anonymize, inspect_config, neural_raw
import gc
import json
import time

def cases():
    freeze=json.loads((ROOT/'data/freeze.json').read_text())
    for name,digest in freeze['files'].items():assert sha(ROOT/'data'/name)==digest, f'Frozen data changed: {name}'
    records=json.loads((ROOT/'data/comparison.json').read_text())['cases']
    for case in records:
        for g in case['gold']:assert case['text'][g['start']:g['end']]==g['text']
    return records

def evaluate(case,found):
    text=case['text'];pred={i for r in found for i in range(r.start,r.end) if not text[i].isspace()}
    gold={i for g in case['gold'] for i in range(g['start'],g['end']) if not text[i].isspace()}
    covered=[]
    for g in case['gold']:
        positions={i for i in range(g['start'],g['end']) if not text[i].isspace()}
        covered.append({'text':g['text'],'fully_covered':positions<=pred,'covered_characters':len(positions&pred),'characters':len(positions)})
    return {'mentions':covered,'fully_covered':sum(x['fully_covered'] for x in covered),
            'gold_mentions':len(covered),'extra_characters':len(pred-gold),
            'negative_with_finding':not case['gold'] and bool(pred)}

def compare(run,aliases):
    records=cases();all_rows=[];summaries={}
    for alias in aliases:
        print('\nЗагружаем:',alias,flush=True)
        started=time.perf_counter();engine=make_analyzer(alias);load=time.perf_counter()-started
        run.save(f'{alias}/configuration.json',{**inspect_config(engine,alias),'load_seconds':load})
        engine.analyze('Куратор Александр Романов, почта curator.demo@example.org.',language='ru',score_threshold=THRESHOLD)
        rows=[]
        for case in records:
            started=time.perf_counter()
            found=engine.analyze(case['text'],language='ru',score_threshold=THRESHOLD,return_decision_process=True)
            elapsed=(time.perf_counter()-started)*1000
            masked=anonymize(case['text'],found)
            row={'config':alias,'id':case['id'],'title':case['title'],'text':case['text'],'gold':case['gold'],
                 'found':serialize(found,case['text']),'raw_model':neural_raw(engine),
                 'masked':masked.text,'analyze_ms':elapsed,'evaluation':evaluate(case,found)}
            run.save(f'{alias}/{case["id"]}.json',row);rows.append(row);all_rows.append(row)
            e=row['evaluation'];print(f"{case['id']} {alias:<8} закрыто {e['fully_covered']}/{e['gold_mentions']}  лишних символов {e['extra_characters']}",flush=True)
        summary={'cases':len(rows),'fully_covered':sum(r['evaluation']['fully_covered'] for r in rows),
             'gold_mentions':sum(r['evaluation']['gold_mentions'] for r in rows),
             'negative_cases':sum(not r['gold'] for r in rows),
             'negative_with_findings':sum(r['evaluation']['negative_with_finding'] for r in rows),
             'extra_characters':sum(r['evaluation']['extra_characters'] for r in rows),
             'timing_note':'One observation per case, after one separate warmup; not a latency benchmark'}
        summaries[alias]=summary;run.save(f'{alias}/summary.json',summary)
        del engine;gc.collect()
    run.save('all-results.json',all_rows);run.save('summary.json',summaries)
    lines=['# Реальные результаты на фиксированных 20 текстах','',
           '| Пример | Конфигурация | Полностью закрыто | Лишних символов |',
           '|---|---|---:|---:|']
    for row in all_rows:
        e=row['evaluation'];lines.append(f"| {row['id']}: {row['title']} | {row['config']} | {e['fully_covered']}/{e['gold_mentions']} | {e['extra_characters']} |")
    (run.path/'table.md').write_text('\n'.join(lines)+'\n')
    return summaries
