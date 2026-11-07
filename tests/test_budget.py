"""Offline checks of exclusive initialization and shared cumulative accounting."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
import json

from init_budget import initialize_budget
from support.gateway import Gateway, ROOT, budget_path


class BudgetTests(TestCase):
    def setUp(self):
        self.temporary=TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.ledger=self.root/'api-budget.json'
        guard=patch('urllib.request.urlopen',side_effect=AssertionError('Network is forbidden in budget tests'))
        guard.start();self.addCleanup(guard.stop)

    def gateway(self,run):
        gateway=Gateway.__new__(Gateway)
        gateway.path=self.root/run
        gateway.ledger_path=self.ledger
        gateway.ledger_lock=self.ledger.with_suffix('.lock')
        return gateway

    def read(self):return json.loads(self.ledger.read_text())

    def test_initializer_refuses_overwrite_and_does_not_reset_spending(self):
        initialize_budget(self.ledger,1)
        self.gateway('first').update_budget('first:1',reservation=.4)
        before=self.ledger.read_bytes()
        with self.assertRaises(FileExistsError):initialize_budget(self.ledger,3)
        self.assertEqual(self.ledger.read_bytes(),before)

    def test_invalid_limits_do_not_create_a_ledger(self):
        for amount in [-1,3.01,float('nan'),float('inf'),True]:
            with self.subTest(amount=amount),self.assertRaises(ValueError):initialize_budget(self.ledger,amount)
            self.assertFalse(self.ledger.exists())

    def test_zero_limit_blocks_paid_reservations(self):
        initialize_budget(self.ledger,0)
        with self.assertRaisesRegex(RuntimeError,'exhausted'):self.gateway('zero').update_budget('zero:1',reservation=.001)
        self.assertEqual(self.read()['calls'],[])

    def test_exhaustion_retains_reservations_after_failed_calls(self):
        initialize_budget(self.ledger,1)
        gateway=self.gateway('first')
        gateway.update_budget('first:1',reservation=.7)
        gateway.update_budget('first:1',status='transport_failed')
        with self.assertRaisesRegex(RuntimeError,'exhausted'):gateway.update_budget('first:2',reservation=.4)
        self.assertEqual(self.read()['reserved_upper_usd'],.7)

    def test_two_runs_share_accounting_and_usage_is_not_settled_twice(self):
        initialize_budget(self.ledger,1)
        first=self.gateway('first');second=self.gateway('second')
        first.update_budget('first:1',reservation=.4)
        second.update_budget('second:1',reservation=.4)
        first.update_budget('first:1',usage={'prompt_tokens':1000,'completion_tokens':100},status='completed')
        before=self.ledger.read_bytes()
        with self.assertRaisesRegex(RuntimeError,'already settled'):
            first.update_budget('first:1',usage={'prompt_tokens':1000,'completion_tokens':100},status='completed')
        self.assertEqual(self.ledger.read_bytes(),before)
        with self.assertRaisesRegex(RuntimeError,'exhausted'):second.update_budget('second:2',reservation=.3)
        ledger=self.read()
        self.assertEqual(len(ledger['calls']),2);self.assertAlmostEqual(ledger['reserved_upper_usd'],.8)
        self.assertAlmostEqual(ledger['usage_estimate_upper_usd'],.00042)

    def test_simultaneous_reservations_cannot_each_take_the_remaining_budget(self):
        initialize_budget(self.ledger,1)
        def reserve(name):
            try:self.gateway(name).update_budget(name+':1',reservation=.6);return True
            except RuntimeError as exc:
                self.assertIn('exhausted',str(exc));return False
        with ThreadPoolExecutor(max_workers=2) as executor:results=list(executor.map(reserve,['first','second']))
        self.assertEqual(sorted(results),[False,True])
        self.assertEqual(len(self.read()['calls']),1);self.assertAlmostEqual(self.read()['reserved_upper_usd'],.6)

    def test_invalid_or_duplicate_reservations_do_not_change_the_ledger(self):
        initialize_budget(self.ledger,1);gateway=self.gateway('first')
        for amount in [0,-1,float('nan'),float('inf'),True]:
            with self.subTest(amount=amount),self.assertRaises(ValueError):gateway.update_budget('first:1',reservation=amount)
        gateway.update_budget('first:1',reservation=.1)
        before=self.ledger.read_bytes()
        with self.assertRaisesRegex(RuntimeError,'already reserved'):gateway.update_budget('first:1',reservation=.1)
        self.assertEqual(self.ledger.read_bytes(),before)

    def test_default_and_explicit_paths(self):
        with patch('support.gateway.settings',return_value={}):self.assertEqual(budget_path(),ROOT/'api-budget.json')
        with patch('support.gateway.settings',return_value={'budget_file':'shared/ledger.json'}):
            self.assertEqual(budget_path(),ROOT/'shared/ledger.json')
        with patch('support.gateway.settings',return_value={'budget_file':str(self.ledger)}):self.assertEqual(budget_path(),self.ledger)

    def test_offline_gateway_needs_no_ledger_but_paid_gateway_requires_one(self):
        with patch('support.gateway.settings',return_value={'budget_file':str(self.ledger)}),patch('support.gateway.ThreadingHTTPServer') as server:
            offline=Gateway(self.root/'offline',key='')
            offline.server.server_close()
            self.assertFalse(self.ledger.exists())
            server.reset_mock()
            with self.assertRaisesRegex(RuntimeError,'init_budget.py'):Gateway(self.root/'paid',key='fixture-not-a-key')
            server.assert_not_called()


if __name__=='__main__':main()
