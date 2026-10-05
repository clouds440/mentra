import sqlite3
from pathlib import Path

from app.core.config import settings


def ensure_database_path() -> Path:
    db_path = Path(settings.sqlite_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def get_connection() -> sqlite3.Connection:
    db_path = ensure_database_path()
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    """Initialise the SQLite database path and verify the file can be opened."""
    with get_connection() as connection:
        connection.execute("SELECT 1")
