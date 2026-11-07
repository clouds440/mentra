"""Private CLI: python scripts/challenge_admin.py --owner UUID export|rebuild|retry."""
import argparse,json
from uuid import UUID
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.db.database import build_engine
from app.assessments.repositories.postgres import AssessmentRepository
from app.challenge.repositories.operations import export_page,rebuild,retry


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner',type=UUID,required=True)
    commands=parser.add_subparsers(dest='command',required=True)
    export=commands.add_parser('export');export.add_argument('--kind',choices=['choices','outcomes'],required=True)
    export.add_argument('--after',default='');export.add_argument('--limit',type=int,default=50)
    build=commands.add_parser('rebuild');build.add_argument('--after',default='');build.add_argument('--limit',type=int,default=32)
    again=commands.add_parser('retry');again.add_argument('--job',type=UUID,required=True)
    args=parser.parse_args();engine=build_engine(settings.database_url)
    try:
        repo=AssessmentRepository(sessionmaker(engine,expire_on_commit=False));owner=str(args.owner)
        if args.command=='export':result=export_page(repo,owner,args.kind,args.after,args.limit)
        elif args.command=='rebuild':result=rebuild(repo,owner,args.after,args.limit)
        else:result=retry(repo,owner,str(args.job))
        print(json.dumps(result,ensure_ascii=False,indent=2,default=str))
    finally:engine.dispose()

if __name__=='__main__':main()
