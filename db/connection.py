"""
db/connection.py
MySQL connection pool for CSC.
Uses mysql.connector.pooling for efficient connection reuse.
"""
import os
from mysql.connector import pooling

_pool: pooling.MySQLConnectionPool | None = None


def _get_pool() -> pooling.MySQLConnectionPool:
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="csc_pool",
            pool_size=int(os.getenv("DB_POOL_SIZE", 5)),
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", 3306)),
            database=os.getenv("DB_NAME", "camp_sc_db"),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD") or os.getenv("DB_PASS", ""),
            charset="utf8mb4",
            use_pure=True,
        )
    return _pool


def get_connection():
    """Return a pooled MySQL connection."""
    return _get_pool().get_connection()


def close_pool():
    """Close all connections in the pool (call at app shutdown)."""
    global _pool
    _pool = None
