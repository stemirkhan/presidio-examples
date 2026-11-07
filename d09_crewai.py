from support.runtime import Run, ROOT
from support.services import privacy_service, post, get
from support.gateway import Gateway, read_key
from support.agent_demo import create_crew, failure_check, validate_report
import json

with Run('D09') as run:
    forbidden = json.loads((ROOT/'data/tracker-gold.json').read_text())['sensitive_values']
    with privacy_service(run) as presidio:
        with Gateway(run.path/'failure-transport',key='',forbidden=forbidden) as test_transport:
            run.show('Проверка остановки при отказе фильтра',failure_check(presidio,test_transport,run))
        if not run.check_only:
            key = read_key()
            with Gateway(run.path/'deepseek',key=key,forbidden=forbidden,max_calls=8) as gateway:
                crew,counters,snapshots = create_crew(presidio,gateway.url,run)
                run.pause('Enter: настоящий запуск CrewAI и DeepSeek')
                output = crew.kickoff()
                raw = output.raw
                (run.path/'answer-raw.txt').write_text(raw)
                report,checks = validate_report(raw,snapshots[-1])
                run.save('report-masked.json',report)
                restored = post(presidio,'/restore',{'text':json.dumps(report,ensure_ascii=False)})
                run.save('report-restored.json',json.loads(restored['text']))
                run.save('vault-local.json',get(presidio,'/state'))
                run.save('validation.json',{**checks,'calls':gateway.forwarded,'counters':counters,
                    'restore_details':restored['details'],'ground_truth_in_prompt':False,'real_crewai':True})
                run.show('Реальный отчет CrewAI',raw)
                run.show('Проверка цитат',checks)
            key=''
