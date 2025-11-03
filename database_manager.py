import sqlite3
import logging
from pathlib import Path
from appdirs import user_config_dir

logger = logging.getLogger(__name__)

DB_DIR = Path(user_config_dir("PigeonHunter"))
DB_FILE = DB_DIR / "processed.db"

class DatabaseManager:

    def __init__(self, db_path=DB_FILE):
        self.db_path = db_path
        self._conn = None
        logger.debug("DatabaseManager initialized with path: %s", db_path)

    def _connect(self):
        try:
            if not self._conn:
                DB_DIR.mkdir(parents=True, exist_ok=True)
                self._conn = sqlite3.connect(self.db_path)
                logger.debug("Connected to database at %s", self.db_path)
        except sqlite3.Error as e:
            logger.critical("Failed to connect to database: %s", e, exc_info=True)
            raise

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.debug("Database connection closed.")

    def create_table(self):
        self._connect()
        try:
            with self._conn:
                self._conn.execute("""
                    CREATE TABLE IF NOT EXISTS processed_emails (
                        message_id TEXT PRIMARY KEY NOT NULL
                    )
                """)
            logger.info("Ensured 'processed_emails' table exists.")
        except sqlite3.Error as e:
            logger.error("Failed to create database table: %s", e, exc_info=True)

    def is_processed(self, message_id):
        self._connect()
        try:
            cursor = self._conn.cursor()
            cursor.execute("SELECT 1 FROM processed_emails WHERE message_id = ?", (message_id,))
            result = cursor.fetchone()
            return result is not None
        except sqlite3.Error as e:
            logger.error("Failed to query database for Message-ID %s: %s", message_id, e)
            return False # Es más seguro re-procesar que fallar

    def add_processed(self, message_id):
        self._connect()
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT OR IGNORE INTO processed_emails (message_id) VALUES (?)",
                    (message_id,)
                )
            logger.debug("Added Message-ID %s to processed list.", message_id)
        except sqlite3.Error as e:
            logger.error("Failed to add Message-ID %s to database: %s", message_id, e)