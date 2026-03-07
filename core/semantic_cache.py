"""
core/semantic_cache.py
In-memory parameter-keyed cache backed by st.session_state.
TTL controlled by CACHE_TTL_MINUTES secret.
"""
import hashlib
import json
import time
from config import get_secret


def build_cache_key(params: dict) -> str:
    """Stable hash of sorted params dict."""
    serialized = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.md5(serialized.encode()).hexdigest()


def _get_cache_store() -> dict:
    import streamlit as st
    if "_cache" not in st.session_state:
        st.session_state["_cache"] = {}
    return st.session_state["_cache"]


def _ttl_seconds() -> float:
    return float(get_secret("CACHE_TTL_MINUTES", "30")) * 60


def get_cached(key: str) -> dict | None:
    """Return cached data if present and not expired, else None."""
    try:
        store = _get_cache_store()
        entry = store.get(key)
        if entry is None:
            return None
        if time.time() - entry["ts"] > _ttl_seconds():
            del store[key]
            return None
        return entry["data"]
    except Exception:
        return None


def set_cache(key: str, data: dict):
    """Store data in cache with current timestamp."""
    try:
        store = _get_cache_store()
        store[key] = {"data": data, "ts": time.time()}
    except Exception:
        pass
