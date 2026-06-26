"""Test configuration.

Disable all optional LLM backends BEFORE the app is imported so the test suite
exercises the deterministic rule-based engine only. This keeps tests fast and
reproducible regardless of any local .env file (load_dotenv does not override
environment variables that are already set).
"""
import os

for _var in ("CUSTOM_API_URL", "CUSTOM_API_KEY", "GROQ_API_KEY"):
    os.environ[_var] = ""
