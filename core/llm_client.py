"""
core/llm_client.py
Thin shared helper — returns a configured Anthropic client.
Centralises SDK init so api_key lookup isn't duplicated across modules.
"""
import anthropic
from config import get_secret


def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=get_secret("ANTHROPIC_API_KEY", ""))
