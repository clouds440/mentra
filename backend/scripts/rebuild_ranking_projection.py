"""Explicit bounded operator recovery; no ledger replay, LLM or belief changes."""
import argparse,json
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.db.database import build_engine
from app.learner.repositories.postgres import PostgresLearnerRepository

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--owner',required=True);parser.add_argument('--after-id',default='');args=parser.parse_args()
    engine=build_engine(settings.database_url)
    try:print(json.dumps(PostgresLearnerRepository(sessionmaker(engine)).rebuild_ranking_projection(args.owner,args.after_id)))
    finally:engine.dispose()
