"""Compare the research image's baked assets with accepted-image manifests."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True); args=parser.parse_args()
    if args.output.exists(): raise RuntimeError('Use a new evidence filename.')
    expected=json.loads(args.manifest.read_text()); report={}
    for role in ('embedding','reranker'):
        manifest=expected[role+'_manifest']; directory=Path('/opt/mentra/models')/role
        mismatches=[]
        for name,digest in manifest['files'].items():
            if name=='model-metadata.json': continue
            path=directory/name
            if not path.is_file(): mismatches.append(name); continue
            with path.open('rb') as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=digest: mismatches.append(name)
        versions={name:importlib.metadata.version(name) for name in manifest['packages']}
        report[role]=dict(asset_mismatches=mismatches,packages=versions,
            packages_match=versions==manifest['packages'],
            identity_matches=json.loads((directory/'model-metadata.json').read_text())==manifest['identity'])
    report['passed']=all(not r['asset_mismatches'] and r['packages_match'] and r['identity_matches'] for r in report.values())
    args.output.write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps(report,indent=2))
    if not report['passed']: raise SystemExit(1)


if __name__=='__main__': main()
