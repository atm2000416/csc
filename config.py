import os


def get_secret(key: str, default=None):
    """Get a secret from st.secrets (Streamlit) or os.getenv (scripts/tests)."""
    try:
        import streamlit as st
        val = st.secrets.get(key)
        if val is not None:
            return str(val)
    except Exception:
        pass
    return os.getenv(key, default)
