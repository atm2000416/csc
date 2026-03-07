"""
db/connection.py
MySQL connection pool for CSC.
Supports Aiven SSL in two modes:
  - Local dev: reads ca.pem from project root if present
  - Streamlit Cloud: reads DB_SSL_CA_CERT secret, writes to tempfile
"""
import os
import tempfile
from mysql.connector import pooling
from config import get_secret

_pool: pooling.MySQLConnectionPool | None = None
_ssl_ca_path: str | None = None


def _prepare_ssl_ca() -> str | None:
    local_ca = os.path.join(os.path.dirname(__file__), "..", "ca.pem")
    if os.path.exists(local_ca):
        return os.path.abspath(local_ca)
    cert = get_secret("DB_SSL_CA_CERT")
    if cert and cert.strip():
        tf = tempfile.NamedTemporaryFile(suffix=".pem", delete=False, mode="w")
        tf.write(cert.strip() + "\n")
        tf.close()
        return tf.name
    return None


def _get_pool() -> pooling.MySQLConnectionPool:
    global _pool, _ssl_ca_path
    if _pool is None:
        _ssl_ca_path = _prepare_ssl_ca()
        ssl_args = {}
        if _ssl_ca_path:
            ssl_args["ssl_ca"] = _ssl_ca_path
            ssl_args["ssl_verify_cert"] = True
        _pool = pooling.MySQLConnectionPool(
            pool_name="csc_pool",
            pool_size=int(get_secret("DB_POOL_SIZE", "5")),
            host=get_secret("DB_HOST", "localhost"),
            port=int(get_secret("DB_PORT", "3306")),
            database=get_secret("DB_NAME", "camp_sc_db"),
            user=get_secret("DB_USER", "root"),
            password=get_secret("DB_PASSWORD", ""),
            charset="utf8mb4",
            use_pure=True,
            **ssl_args,
        )
    return _pool


def get_connection():
    """Return a pooled MySQL connection."""
    return _get_pool().get_connection()


def close_pool():
    """Close all connections in the pool (call at app shutdown)."""
    global _pool
    _pool = None
