"""Offline records only. No provider call or production database mutation."""
import argparse,json
from pathlib import Path
from app.learner.prospective import evaluate,blinded_ablation

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('records',type=Path);parser.add_argument('--protocol',type=Path)
    parser.add_argument('--blind-ablation',type=int,help='Prepare paired cases with this preregistered seed; output contains PRIVATE arm mapping')
    args=parser.parse_args();rows=[json.loads(line) for line in args.records.read_text(encoding='utf-8').splitlines() if line.strip()]
    if args.blind_ablation is not None:result=blinded_ablation(rows,args.blind_ablation)
    else:
        if not args.protocol:parser.error('--protocol is required')
        result=evaluate(rows,json.loads(args.protocol.read_text(encoding='utf-8')))
    print(json.dumps(result,indent=2))
