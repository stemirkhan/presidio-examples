from support.runtime import Run, serialize
from support.pseudonyms import Vault, mask, restore
from presidio_analyzer import AnalyzerEngine

text = 'Please ask John Smith to reply to john.smith@example.com.'

with Run('D10b') as run:
    found = AnalyzerEngine().analyze(text,language='en',entities=['PERSON','EMAIL_ADDRESS'])
    vault = Vault()
    masked = mask(text,found,vault)
    person = next(t for t in vault.mapping if vault.types[t]=='PERSON')
    secret = vault.issue('ACCESS_TOKEN','FICTIONAL-ACCESS-ONLY')
    # This string is explicitly an authored test of an operator, not an LLM response.
    answer = f'{person} должен ответить. Повтор: {person}. Секрет: {secret}. Неизвестно: [PERSON_999_deadbeef].'
    run.show('Авторская тестовая строка, не ответ LLM',answer)
    run.pause('Enter: найти метки в новом тексте и восстановить разрешенные значения')
    result, details = restore(answer,vault,allowed_types=('PERSON','EMAIL_ADDRESS'))
    run.show('Фактический результат DeanonymizeEngine',result.text)
    checks={'both_names_restored':result.text.count('John Smith')==2,'secret_stays_hidden':secret in result.text,
            'unknown_unchanged':'[PERSON_999_deadbeef]' in result.text,'fresh_positions':details['current_response_spans'][0]['start']==0}
    run.save('result.json',{'input':text,'found':serialize(found,text),'masked':masked.text,'vault':vault.state(),
             'authored_test_response_not_llm':answer,'restored':result.text,'details':details,'checks':checks,'api_called':False})
    assert all(checks.values())
