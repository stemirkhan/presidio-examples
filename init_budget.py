"""Create a fresh local spending ledger once. No key, model or network is used."""
from datetime import datetime, timezone
import argparse
import json
import os

from support.gateway import RATES, budget_path, validate_limit


def initialize_budget(path, limit_usd):
    limit=validate_limit(limit_usd)
    ledger={
        'approved_usd':limit,
        'approved_on':datetime.now(timezone.utc).isoformat(),
        'reserved_upper_usd':0.0,
        'usage_estimate_upper_usd':0.0,
        'calls':[],
        'rates':dict(RATES),
        'pricing_source':'Example estimates configured in support/gateway.py; verify provider pricing before paid calls',
        'note':'Reservations are cumulative across runs and are not released. Local estimates are not a provider billing cap.',
    }
    path.parent.mkdir(parents=True,exist_ok=True)
    # O_EXCL also refuses existing files and symlinks; no reset/overwrite option.
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w',encoding='utf-8') as file:
        json.dump(ledger,file,ensure_ascii=False,indent=2);file.write('\n');file.flush();os.fsync(file.fileno())
    return ledger


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit-usd',required=True,type=float,help='Local cumulative limit, from 0 to 3 USD; 0 disables paid calls')
    parser.add_argument('--budget-file',help='Optional ledger path; defaults to local.json budget_file or project api-budget.json')
    args=parser.parse_args()
    try:
        path=budget_path(args.budget_file)
        ledger=initialize_budget(path,args.limit_usd)
    except (OSError,ValueError) as exc:
        parser.error(f'{exc}. Existing budget ledgers are never overwritten.')
    print(f'Created {path}\nLocal cumulative limit: ${ledger["approved_usd"]:g}. No API call was made.')


if __name__=='__main__':main()
