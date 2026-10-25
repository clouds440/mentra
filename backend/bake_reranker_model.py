"""Optional build-time cross-encoder assets; runtime never downloads models."""
import json
import os
from pathlib import Path

os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
from huggingface_hub import model_info, snapshot_download


def bake_model(model_name, path=Path('/opt/mentra/models/reranker')):
    """Pin the downloaded assets to a resolved revision and record their identity."""
    info = model_info(model_name)
    files = {f.rfilename for f in info.siblings}
    weight = next((f for f in ('model.safetensors', 'pytorch_model.bin') if f in files), None)
    if not weight:
        raise RuntimeError('The reranker has no supported local PyTorch weights.')
    snapshot_download(repo_id=model_name, revision=info.sha, local_dir=str(path), allow_patterns=[weight, '*.json', 'vocab.txt', 'merges.txt', '*.model'])
    (path / 'model-metadata.json').write_text(json.dumps(dict(model_name=model_name, model_version=info.sha)), encoding='utf-8')


if __name__ == '__main__':
    model_name = os.environ.get('RAG_RERANKER_MODEL', '').strip()
    if model_name:
        bake_model(model_name)
