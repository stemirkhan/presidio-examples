"""Recompute the recorded D07 metrics and validate selected saved evidence offline."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text())


def main():
    snapshot = read(ROOT / 'evidence/snapshot.json')
    data = ROOT / 'data/comparison.json'
    assert hashlib.sha256(data.read_bytes()).hexdigest() == snapshot['comparison_dataset_sha256']
    rows = read(ROOT / 'evidence/recorded/D07/all-results.json')
    assert len(rows) == len({(r['id'], r['config']) for r in rows}) == 60
    summary = {}
    for alias in ('baseline', 'fastino', 'metrika'):
        selected = [r for r in rows if r['config'] == alias]
        assert len(selected) == 20
        full = total = extra = negatives = 0
        for row in selected:
            text = row['text']; pred = set(); truth = set()
            for item in row['found']:
                assert text[item['start']:item['end']] == item['text']
                pred.update(range(item['start'], item['end']))
            for item in row['gold']:
                span = set(range(item['start'], item['end']))
                assert text[item['start']:item['end']] == item['text']
                truth.update(span)
                full += all(i in pred for i in span if not text[i].isspace())
                total += 1
            extra += sum(i not in truth and not text[i].isspace() for i in pred)
            negatives += not row['gold'] and any(not text[i].isspace() for i in pred)
        summary[alias] = {'fully_covered': full, 'gold_mentions': total, 'extra_characters': extra,
                          'negative_with_findings': negatives, 'negative_cases': 4}
        assert summary[alias] == snapshot['comparison'][alias]
    for path, digest in read(ROOT / 'evidence/recorded/checksums.json').items():
        assert hashlib.sha256((ROOT / 'evidence/recorded' / path).read_bytes()).hexdigest() == digest, path
    agent = read(ROOT / 'evidence/recorded/D09/validation.json')
    assert agent['calls'] == snapshot['crewai']['api_calls'] == 2
    assert agent['counters']['tools'] == 1
    proxy = read(ROOT / 'evidence/recorded/D11/validation.json')
    assert proxy['provider_calls'] == 2
    assert proxy['failure_check']['gateway_calls_during_failure'] == 0
    print(json.dumps({'passed': True, 'comparison': summary, 'recorded_api_calls_only': True,
                      'new_api_calls': 0}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
