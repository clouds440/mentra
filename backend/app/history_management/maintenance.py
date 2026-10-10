"""Bounded per-owner maintenance; no always-running additional worker required."""
import argparse
from uuid import UUID


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--owner', required=True, type=UUID)
    parser.add_argument('--limit', type=int, default=100)
    args = parser.parse_args()
    from app.db.database import get_session_factory
    from .repositories.postgres import MemoryRepository
    from app.core.logging import configure_logging, workflow_logger
    configure_logging('memory-maintenance')
    with workflow_logger.workflow('memory.maintenance') as execution:
        result = MemoryRepository(get_session_factory()).maintain(str(args.owner), max(1, min(100, args.limit)))
        execution.outcome = 'success'
        workflow_logger.event('maintenance.completed', result=result)


if __name__ == '__main__':
    main()
