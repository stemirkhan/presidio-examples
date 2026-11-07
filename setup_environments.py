"""Recreate three isolated Python 3.12 environments on Linux/WSL."""
from pathlib import Path
import json
import shutil
import subprocess
import sys


def main():
    if sys.version_info[:2]!=(3,12):
        raise SystemExit('Требуется Python 3.12: запустите python3.12 setup_environments.py')
    root=Path(__file__).resolve().parent
    uv=shutil.which('uv')
    if uv is None:raise SystemExit('Install uv first or use the pip commands in README.md')
    environments=[('.venv','requirements-core.lock'),('.venv-agent','requirements-agent.lock'),('.venv-proxy','requirements-proxy.lock')]
    for folder,lock in environments:
        if not (root/lock).is_file():raise SystemExit(f'Не найден файл зависимостей: {lock}')
        target=root/folder
        py=target/'bin/python'
        if py.exists():
            version=subprocess.run([str(py),'-c','import json,sys; print(json.dumps(list(sys.version_info[:2])))'],
                                   check=True,text=True,capture_output=True)
            if json.loads(version.stdout)!=[3,12]:
                raise SystemExit(f'{folder} использует другую версию Python. Переименуйте окружение и повторите установку с Python 3.12.')
        else:
            subprocess.run([uv,'venv','--python',sys.executable,'--cache-dir',str(root/'cache/uv'),str(target)],check=True)
        command=[uv,'pip','install','--python',str(py),'--cache-dir',str(root/'cache/uv'),'-r',str(root/lock)]
        if folder=='.venv':command+=['--extra-index-url','https://download.pytorch.org/whl/cpu','--index-strategy','unsafe-best-match']
        subprocess.run(command,check=True)
    print('Then run .venv/bin/python prepare_models.py if the frozen weights are not already available locally.')


if __name__=='__main__':main()
