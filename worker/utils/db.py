import logging
from contextlib import contextmanager
from typing import Dict, Any, List, Optional, Generator
import psycopg
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

from worker.config import DatabaseConfig
import threading

logger = logging.getLogger(__name__)


class DatabaseHelper:
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._pool: Optional[ConnectionPool] = None

    def initialize_pool(self):
        """Initialize the connection pool."""
        try:
            self._pool = ConnectionPool(
                conninfo=self.config.connection_string,
                min_size=1,
                max_size=self.config.pool_size + self.config.max_overflow,
                open=True
            )
            logger.info("Database connection pool initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise

    def close_pool(self):
        """Close all connections in the pool."""
        if self._pool:
            self._pool.close()
            logger.info("Database connection pool closed")


# Module-level shared helper for reusing a single connection pool
_SHARED_HELPER: Optional[DatabaseHelper] = None
_INIT_LOCK = threading.Lock()


def get_shared_db_helper(config: DatabaseConfig) -> DatabaseHelper:
    """Return a process-wide shared DatabaseHelper with an initialized pool.

    Initializes the pool on first use and reuses it for subsequent calls.
    """
    global _SHARED_HELPER
    if _SHARED_HELPER is None:
        with _INIT_LOCK:
            if _SHARED_HELPER is None:
                helper = DatabaseHelper(config)
                helper.initialize_pool()
                _SHARED_HELPER = helper
                logger.info("Shared database helper initialized")
    return _SHARED_HELPER


def close_shared_pool() -> None:
    """Close the shared connection pool if initialized."""
    global _SHARED_HELPER
    if _SHARED_HELPER is not None:
        try:
            _SHARED_HELPER.close_pool()
        finally:
            _SHARED_HELPER = None
            logger.info("Shared database helper cleared")

    @contextmanager
    def get_connection(self) -> Generator[psycopg.Connection, None, None]:
        """Get a connection from the pool."""
        if not self._pool:
            raise RuntimeError("Database pool not initialized")

        with self._pool.connection() as conn:
            try:
                yield conn
            except Exception as e:
                conn.rollback()
                logger.error(f"Database operation error: {e}")
                raise

    @contextmanager
    def get_cursor(self, commit: bool = True) -> Generator[psycopg.Cursor, None, None]:
        """Get a cursor with automatic transaction management."""
        with self.get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                try:
                    yield cursor
                    if commit:
                        conn.commit()
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Database cursor operation error: {e}")
                    raise

    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results."""
        with self.get_cursor(commit=False) as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def execute_update(self, query: str, params: Optional[tuple] = None) -> int:
        """Execute an INSERT/UPDATE/DELETE query and return affected row count."""
        with self.get_cursor(commit=True) as cursor:
            cursor.execute(query, params)
            return cursor.rowcount

    def upsert_recipe(self, recipe_id: str, s3_raw_key: str, content_sha256: str,
                     status: str = 'succeeded') -> bool:
        """Upsert recipe record."""
        query = """
        INSERT INTO recipes (id, s3_raw_key, content_sha256, status, updated_at)
        VALUES (%s, %s, %s, %s, NOW())
        ON CONFLICT (id) DO UPDATE SET
            s3_raw_key = EXCLUDED.s3_raw_key,
            content_sha256 = EXCLUDED.content_sha256,
            status = EXCLUDED.status,
            updated_at = NOW()
        """
        try:
            rows_affected = self.execute_update(query, (recipe_id, s3_raw_key, content_sha256, status))
            logger.info(f"Upserted recipe {recipe_id}, rows affected: {rows_affected}")
            return True
        except Exception as e:
            logger.error(f"Failed to upsert recipe {recipe_id}: {e}")
            raise

    def upsert_recipe_ocr(self, recipe_id: str, s3_ocr_key: str, ocr_engine: str,
                         ocr_version: str, page_count: int = 1) -> bool:
        """Upsert recipe OCR record."""
        query = """
        INSERT INTO recipe_ocr (recipe_id, s3_ocr_key, ocr_engine, ocr_version, page_count, created_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
        ON CONFLICT (recipe_id) DO UPDATE SET
            s3_ocr_key = EXCLUDED.s3_ocr_key,
            ocr_engine = EXCLUDED.ocr_engine,
            ocr_version = EXCLUDED.ocr_version,
            page_count = EXCLUDED.page_count,
            created_at = NOW()
        """
        try:
            rows_affected = self.execute_update(query, (recipe_id, s3_ocr_key, ocr_engine, ocr_version, page_count))
            logger.info(f"Upserted recipe OCR for {recipe_id}, rows affected: {rows_affected}")
            return True
        except Exception as e:
            logger.error(f"Failed to upsert recipe OCR for {recipe_id}: {e}")
            raise

    def get_recipe_by_id(self, recipe_id: str) -> Optional[Dict[str, Any]]:
        """Get recipe by ID."""
        query = "SELECT * FROM recipes WHERE id = %s"
        try:
            results = self.execute_query(query, (recipe_id,))
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Failed to get recipe {recipe_id}: {e}")
            raise

    def get_recipe_ocr_by_id(self, recipe_id: str) -> Optional[Dict[str, Any]]:
        """Get recipe OCR by recipe ID."""
        query = "SELECT * FROM recipe_ocr WHERE recipe_id = %s"
        try:
            results = self.execute_query(query, (recipe_id,))
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Failed to get recipe OCR for {recipe_id}: {e}")
            raise
