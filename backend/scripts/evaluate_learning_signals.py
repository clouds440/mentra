import json,sys
from pathlib import Path
from app.learner.signal_evaluation import signal_gate

data=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
report=signal_gate(data['turns'])
Path(sys.argv[2]).write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
raise SystemExit(0 if report['G10'] else 2)
