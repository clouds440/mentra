"""Portable model artifact manifest for builds and offline integrity checks."""
import hashlib
import importlib.metadata
import json
from pathlib import Path


def write_manifest(directory, *, role):
    directory = Path(directory)
    identity = json.loads((directory/'model-metadata.json').read_text())
    files = {}
    for path in sorted(directory.rglob('*')):
        relative = path.relative_to(directory)
        if path.is_file() and '.cache' not in relative.parts and path.name != 'model-artifacts.json':
            with path.open('rb') as stream:
                files[relative.as_posix()] = hashlib.file_digest(stream, 'sha256').hexdigest()
    packages = {}
    for name in ('torch', 'sentence-transformers', 'transformers', 'tokenizers'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = 'not-installed'
    manifest = dict(format=1, identity=identity, role=role, files=files, packages=packages,
        policy=dict(max_length=512 if role=='reranker' else 'baked-model-limit', normalized=role == 'embedding',
                    pooling=json.loads((directory/'1_Pooling/config.json').read_text()) if (directory/'1_Pooling/config.json').exists() else None,
                    retrieval_roles=['query: ', 'passage: '] if role == 'embedding' else []))
    (directory/'model-artifacts.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return manifest


def verify_manifest(directory, *, role=None):
    directory = Path(directory).resolve()
    manifest_path = directory/'model-artifacts.json'
    if not manifest_path.exists():
        return False  # Historical baked assets predate manifests.
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('format') != 1 or not manifest.get('files'):
        raise ValueError('Invalid model artifact manifest.')
    if role and manifest.get('role') != role:
        raise ValueError('Model artifact role mismatch.')
    for package, expected in manifest.get('packages', {}).items():
        if expected == 'not-installed':
            continue
        try:
            actual=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as error:
            raise ValueError('Model runtime package missing.') from error
        if actual != expected:
            raise ValueError('Model runtime package mismatch.')
    for name, expected in manifest['files'].items():
        path = (directory/name).resolve()
        if not path.is_relative_to(directory) or not path.is_file():
            raise ValueError('Invalid model artifact path.')
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                raise ValueError('Model artifact checksum mismatch.')
    actual_files={p.relative_to(directory).as_posix() for p in directory.rglob('*')
        if p.is_file() and '.cache' not in p.relative_to(directory).parts and p.name!='model-artifacts.json'}
    if actual_files != set(manifest['files']):
        raise ValueError('Unrecorded model artifact files.')
    if manifest['identity'] != json.loads((directory/'model-metadata.json').read_text()):
        raise ValueError('Model artifact identity mismatch.')
    return True
