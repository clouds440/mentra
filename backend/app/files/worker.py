"""Private-file cleanup; no models or embeddings initialized."""

import signal
from threading import Event


def main():
    from app.core.config import settings

    settings.database_role = "worker"
    from app.core.logging import configure_logging, logger
    from app.db.database import init_db
    from .factory import create_files

    configure_logging("files-worker")
    init_db()
    files = create_files()
    files.check_configuration()
    stopping = Event()
    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, lambda *_: stopping.set())
    try:
        while not stopping.is_set():
            try:
                count = files.cleanup(limit=10)
                if count:
                    logger.info("File cleanup processed %s assets", count)
            except Exception:
                logger.warning("File cleanup failed; retrying next batch")
            stopping.wait(10)
    finally:
        files.close()


if __name__ == "__main__":
    main()
