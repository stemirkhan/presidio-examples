"""Regression checks for repeated sanitization, using real Presidio operators.

Schema-forced names do not use the detector. Construct just the service state
needed by that path so these checks require neither model weights nor an API.
"""
import copy
import json
import unittest

from support.privacy_service import Privacy
from support.pseudonyms import Vault, restore


class RepeatedSanitizationTests(unittest.TestCase):
    def setUp(self):
        self.privacy = Privacy.__new__(Privacy)
        self.privacy.vault = Vault()
        self.payload = {
            'id': 'DEMO-17',
            'assignee': {'name': 'Анна Примерова'},
            'reviewer': {'name': 'Олег Тестовый'},
            'participants': [{'name': 'Анна Примерова'}],
        }

    def test_tool_tree_and_message_pass_keep_the_same_names(self):
        first = self.privacy.tree(self.payload)
        state = copy.deepcopy(self.privacy.vault.state())
        second = self.privacy.tree(first)
        message = {'role': 'tool', 'content': json.dumps(first, ensure_ascii=False)}
        third = json.loads(self.privacy.messages([message])[0]['content'])
        self.assertEqual(second, first)
        self.assertEqual(third, first)
        self.assertEqual(self.privacy.vault.state(), state)
        self.assertEqual(first['id'], self.payload['id'])
        self.assertEqual(first['assignee']['name'], first['participants'][0]['name'])
        self.assertNotEqual(first['assignee']['name'], first['reviewer']['name'])
        restored, _ = restore(json.dumps(third, ensure_ascii=False), self.privacy.vault, allowed_types=['PERSON'])
        self.assertEqual(json.loads(restored.text), self.payload)
        self.assertEqual(self.payload['assignee']['name'], 'Анна Примерова')

    def test_known_tag_alone_stays_stable_without_a_forced_type(self):
        tag = self.privacy.text('Анна Примерова', forced='PERSON')
        self.assertEqual(self.privacy.text(tag), tag)
        self.assertEqual(len(self.privacy.vault.mapping), 1)

    def test_a_foreign_or_partial_tag_is_not_trusted(self):
        foreign = '[PERSON_99_1234abcd]'
        issued = self.privacy.tree({'name': foreign})['name']
        self.assertNotEqual(issued, foreign)
        self.assertEqual(self.privacy.vault.mapping[issued], foreign)
        embedded = issued + ' дополнительный текст'
        wrapped = self.privacy.text(embedded, forced='PERSON')
        self.assertNotEqual(wrapped, embedded)
        self.assertEqual(self.privacy.vault.mapping[wrapped], embedded)

    def test_repeat_pass_does_not_change_a_secret_into_a_person(self):
        tag = self.privacy.vault.issue('ACCESS_TOKEN', 'FICTIONAL-ACCESS-ONLY')
        processed = self.privacy.tree({'name': tag})['name']
        self.assertEqual(processed, tag)
        result, details = restore(processed, self.privacy.vault, allowed_types=['PERSON'])
        self.assertEqual(result.text, tag)
        self.assertEqual(details['withheld'], [tag])


if __name__ == '__main__':
    unittest.main()
