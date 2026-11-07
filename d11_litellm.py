from support.runtime import Run
from support.services import privacy_service, post
from support.gateway import Gateway, read_key
from support.proxy_demo import proxy_service
import json
import urllib.error

text = 'Клиент Марина Соколова, почта marina.sokolova@example.com. Подготовьте одну короткую фразу: кому нужно ответить. Сохраните полученные метки буквально.'
forbidden = ['Марина Соколова','marina.sokolova@example.com']

with Run('D11') as run:
    key = '' if run.check_only else read_key()
    with privacy_service(run) as presidio:
        with Gateway(run.path/'deepseek',key=key,forbidden=forbidden,max_calls=4) as gateway:
            with proxy_service(run,presidio,gateway) as (proxy,proxy_headers):
                post(presidio,'/fault',{'enabled':True})
                before = gateway.received
                try:
                    post(proxy,'/v1/chat/completions',{'model':'demo-deepseek','messages':[{'role':'user','content':text}],'guardrails':['presidio-mask']},headers=proxy_headers)
                    blocked = False
                except urllib.error.HTTPError as exc:
                    blocked = True
                    run.save('failure-response.json',{'status':exc.code,'body':exc.read().decode()})
                finally:
                    post(presidio,'/fault',{'enabled':False})
                check = {'filter_failure_blocked':blocked,'gateway_calls_during_failure':gateway.received-before}
                run.show('Реальная проверка отказа фильтра',check)
                run.save('failure-check.json',check)
                assert blocked and gateway.received==before
                results = {}
                if not run.check_only:
                    for guardrail in ['presidio-mask','presidio-restore']:
                        run.pause('Enter: запрос через '+guardrail)
                        request = {'model':'demo-deepseek','messages':[{'role':'user','content':text}],'guardrails':[guardrail]}
                        run.save(guardrail+'-client-request.json',request)
                        response = post(proxy,'/v1/chat/completions',request,timeout=180,headers=proxy_headers)
                        run.save(guardrail+'-client-response.json',response)
                        content=response['choices'][0]['message']['content']
                        provider_content=gateway.responses[-1]['choices'][0]['message']['content']
                        results[guardrail]={'provider_answer':provider_content,'client_answer':content,
                            'originals_in_client_answer':[value for value in forbidden if value in content]}
                        run.show(guardrail,content)
                run.save('validation.json',{'real_litellm_proxy':True,'real_presidio_services':True,'provider_calls':gateway.forwarded,
                    'known_originals_checked_at_egress':forbidden,'failure_check':check,'streaming_tested':False,
                    'output_scan_enabled':False,'results':results})
    key=''
