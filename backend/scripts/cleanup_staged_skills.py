"""Operator preview/apply. Only unreferenced unpublished stages older than 7 days."""
import argparse,json
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.db.database import build_engine
from app.learner.repositories.postgres import PostgresLearnerRepository

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--owner',required=True)
    parser.add_argument('--apply-digest',help='Apply exactly the reviewed current preview; otherwise preview only')
    parser.add_argument('--after-id',default='',help='Continue from the previous preview next_cursor')
    args=parser.parse_args()
    engine=build_engine(settings.database_url)
    try:
        result=PostgresLearnerRepository(sessionmaker(engine)).cleanup_staged_skills(args.owner,
            apply=bool(args.apply_digest),expected_digest=args.apply_digest,after_id=args.after_id)
        print(json.dumps(result,indent=2))
    finally: engine.dispose()
