"""Owned operator export. No answers, keys, quotes or uploaded artifacts leave DB."""
import argparse,json
from hashlib import sha256
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.db.database import build_engine
from app.assessments.repositories.tables import prediction_snapshots as p,attempts as t,assessments as a

def export(session,owner):
    query=select(p,t.c.grades,t.c.submitted_at,t.c.reported_assistance,a.c.questions,a.c.preferences,a.c.revision.label('current_revision')).join(t,
        (t.c.learner_id==p.c.learner_id)&(t.c.id==p.c.attempt_id)).join(a,(a.c.learner_id==t.c.learner_id)&(a.c.id==t.c.assessment_id)).where(
        p.c.learner_id==owner,t.c.state=='graded').order_by(p.c.captured_at,p.c.attempt_id,p.c.question_id).execution_options(yield_per=100)
    for row in session.execute(query).mappings():
        q=next((q for q in row['questions'] if q['id']==row['question_id']),None)
        grade=next((g for g in row['grades'] or [] if g['question_id']==row['question_id']),None)
        if not q or not grade or not row['submitted_at']:continue
        yield dict(student=sha256(owner.encode()).hexdigest(),attempt_id=row['attempt_id'],question_id=row['question_id'],
            captured_at=row['captured_at'].isoformat(),outcome_at=row['submitted_at'].isoformat(),item_family=row['item_family'],
            expected_score=row['expected_score'],baseline_recent=row['baseline_recent'],baseline_band=row['baseline_band'],
            supported=row['supported'],first_exposure=row['first_exposure'],observed=grade['score']/q['marks'],
            assistance=row['reported_assistance'],language=row['preferences'].get('language','unlabelled'),answer_mode=row['answer_mode'],
            valid=q.get('validation',{}).get('state')!='invalidated' and row['assessment_revision']==row['current_revision'],
            independently_reviewed=False,synthetic=True,protocol=row['protocol'])

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--owner',required=True);args=parser.parse_args()
    engine=build_engine(settings.database_url)
    try:
        with sessionmaker(engine)() as session:
            from sqlalchemy import text
            session.execute(text('SET TRANSACTION READ ONLY'))
            for row in export(session,args.owner):print(json.dumps(row))
    finally:engine.dispose()
