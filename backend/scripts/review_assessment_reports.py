"""Private, owner-scoped report queue and preview/apply correction workflow."""
import argparse
import json
from pathlib import Path
from uuid import UUID
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.db.database import build_engine
from app.assessments.repositories.postgres import AssessmentRepository
from app.assessments.review_queue import pending_reports, reported_item, correct_report
from app.learner import LearnerEngine
from app.learner.repositories.postgres import PostgresLearnerRepository


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner', required=True, type=UUID)
    commands = parser.add_subparsers(dest='command', required=True)
    queue = commands.add_parser('list', help='List pending reports without keys or student answers')
    queue.add_argument('--after')
    queue.add_argument('--limit', type=int, default=50)
    show = commands.add_parser('show', help='PRIVATE: show the current item/key and correction template')
    show.add_argument('--report', type=UUID, required=True)
    correct = commands.add_parser('correct', help='Preview, or apply the exact previewed trusted correction')
    correct.add_argument('--report', type=UUID, required=True)
    correct.add_argument('--file', type=Path, required=True, help='JSON object from correction_template')
    correct.add_argument('--expected-revision', type=int, required=True)
    correct.add_argument('--operation-id', type=UUID, required=True)
    correct.add_argument('--apply-digest')
    args = parser.parse_args()
    engine = build_engine(settings.database_url)
    try:
        sessions = sessionmaker(engine, expire_on_commit=False)
        repository = AssessmentRepository(sessions)
        learner = LearnerEngine(PostgresLearnerRepository(sessions))
        repository.withdraw_item_evidence = learner.withdraw_assessment_evidence_in_transaction
        owner = str(args.owner)
        if args.command == 'list':
            result = pending_reports(repository, owner, after=args.after, limit=args.limit)
        elif args.command == 'show':
            result = reported_item(repository, owner, str(args.report))
        else:
            result = correct_report(repository, owner, str(args.report), json.loads(args.file.read_text(encoding='utf-8')),
                expected_revision=args.expected_revision, operation_id=str(args.operation_id), apply_digest=args.apply_digest)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
