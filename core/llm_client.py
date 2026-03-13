"""
core/llm_client.py
Thin shared helper — returns a configured Anthropic client.
Centralises SDK init so api_key lookup isn't duplicated across modules.

Timeout: 30s default (Anthropic SDK default is 10 minutes — without this,
a stalled API call hangs the entire Streamlit app indefinitely).
"""
import anthropic
from config import get_secret

_TIMEOUT_SECONDS = 30.0


def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=get_secret("ANTHROPIC_API_KEY", ""),
        timeout=_TIMEOUT_SECONDS,
    )
