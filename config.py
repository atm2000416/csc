import os


def get_secret(key: str, default=None):
    """Get a secret from st.secrets (Streamlit) or os.getenv (scripts/tests)."""
    try:
        import streamlit as st
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key, default)
