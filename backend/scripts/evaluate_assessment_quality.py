"""python scripts/evaluate_assessment_quality.py reviewed-corpus.json report.json"""
import json,sys
from pathlib import Path
from app.assessments.evaluation import quality_gate,grading_gate

corpus=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
report=dict(items=quality_gate(corpus.get('items',[])),grading=grading_gate(corpus.get('grades',[])))
Path(sys.argv[2]).write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
raise SystemExit(0 if report['items']['decision']=='promote' and report['grading']['passed'] else 2)
