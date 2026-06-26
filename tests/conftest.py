"""Test configuration.

By default the optional LLM backends are DISABLED so the suite is deterministic,
fast, and offline. The LLM logic itself is still covered by mocked backends
(see test_llm_safety.py and test_edge_adversarial.py::TestMockedLLM).

Tests that hit a REAL configured backend (your .env) are marked `llm` and only
run when you opt in:

    RUN_LLM_TESTS=1 uv run pytest -m llm -v       # only the live LLM tests
    RUN_LLM_TESTS=1 uv run pytest -v              # everything, incl. live LLM

Without RUN_LLM_TESTS=1, `llm`-marked tests are skipped.
"""
import os

import pytest

_RUN_LLM = os.getenv("RUN_LLM_TESTS", "").strip().lower() in ("1", "true", "yes", "on")

# Disable real LLM backends for all standard (non-live) tests. load_dotenv() in
# app.main does not override these because they are already set.
for _var in ("CUSTOM_API_URL", "CUSTOM_API_KEY", "GROQ_API_KEY"):
    os.environ[_var] = ""


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "llm: requires a live LLM backend; run with RUN_LLM_TESTS=1 and a configured .env",
    )


def pytest_collection_modifyitems(config, items):
    if _RUN_LLM:
        return
    skip_live = pytest.mark.skip(
        reason="live LLM test — set RUN_LLM_TESTS=1 (and configure .env) to run"
    )
    for item in items:
        if "llm" in item.keywords:
            item.add_marker(skip_live)
