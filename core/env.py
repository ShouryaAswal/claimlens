"""
core/env.py
---------------
Single place .env loading happens. Import this (for its side effect) from
anywhere that reads an environment variable at import time -- currently
core/config.py (CLAIMLENS_OCR_ENGINE) and core/llm_client.py (GROQ_API_KEY,
GOOGLE_API_KEY, CLAIMLENS_GROQ_MODEL, CLAIMLENS_GEMINI_MODEL).

Safe to import from multiple modules -- python-dotenv's load_dotenv() is
idempotent, and by default it does NOT override a variable that's already
set in the real environment (so a real `export GROQ_API_KEY=...` in your
shell always wins over a stale value sitting in .env).

If python-dotenv isn't installed, this degrades to "environment variables
still work if exported the normal way" rather than crashing -- same
graceful-degradation pattern as every other optional dependency in this
project (PaddleOCR, openai, google-genai).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv

    # find_dotenv() with usecwd=True searches the current working directory
    # and walks upward -- works whether you run `python3 scripts/foo.py`
    # from the repo root or from inside scripts/.
    _was_loaded = load_dotenv(override=False)
    if _was_loaded:
        logger.debug(".env file loaded.")
    else:
        logger.debug("No .env file found -- relying on shell-exported environment variables only.")
except ImportError:
    logger.debug(
        "python-dotenv not installed -- a .env file (if present) will NOT be "
        "auto-loaded. `pip install python-dotenv` to enable it, or just "
        "export the variables in your shell instead."
    )
