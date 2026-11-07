from support.runtime import Run, serialize
from support.pseudonyms import Vault, mask
from presidio_analyzer import AnalyzerEngine

text = 'John Smith opened the issue. John Smith confirmed john.smith@example.com.'

with Run('D10') as run:
    found = AnalyzerEngine().analyze(text,language='en',entities=['PERSON','EMAIL_ADDRESS'])
    vault = Vault()
    masked = mask(text,found,vault)
    run.show('Исходный текст',text)
    run.pause('Enter: заменить устойчивыми метками')
    run.show('После замены',masked.text)
    run.show('Локальный словарь; не отправляется модели',vault.state())
    run.save('result.json',{'input':text,'found':serialize(found,text),'masked':masked.text,'vault':vault.state()})
