"""Download only the two frozen GLiNER checkpoints for another workstation."""
import json
from pathlib import Path
from huggingface_hub import snapshot_download

root=Path(__file__).resolve().parent
specs=json.loads((root/'data/models.json').read_text())
for alias,spec in specs.items():
    print('Download:',spec['id'],spec['revision'],flush=True)
    snapshot_download(repo_id=spec['id'],revision=spec['revision'],local_dir=root/'models'/alias,
        allow_patterns=['config.json','encoder_config/*','model.safetensors','tokenizer*','special_tokens_map.json','README.md','NOTICE','LICENSE*'])
