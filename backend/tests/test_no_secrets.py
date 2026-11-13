"""Guard against real secrets in files that are pushed to GitHub (NFR-021).

.env is git-ignored and holds the real values; .env.example is committed and
must only contain placeholders.
"""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

SECRET_PATTERNS = {
    "Google / Gemini API key": re.compile(r"\b(AIza[0-9A-Za-z_-]{20,}|AQ\.[0-9A-Za-z_-]{20,})"),
    "Anthropic API key": re.compile(r"\bsk-ant-[0-9A-Za-z_-]{20,}"),
    "OpenAI-style key": re.compile(r"\bsk-[0-9A-Za-z]{32,}"),
}


def test_env_example_has_only_placeholders():
    text = (BACKEND / ".env.example").read_text(encoding="utf-8")
    found = [name for name, pattern in SECRET_PATTERNS.items() if pattern.search(text)]
    assert not found, (f".env.example contains a real {', '.join(found)}. Put real values in "
                       f".env (git-ignored) and keep placeholders in .env.example.")


def test_env_file_is_git_ignored():
    ignore = (BACKEND.parent / ".gitignore").read_text(encoding="utf-8")
    assert re.search(r"^\.env$", ignore, re.MULTILINE)
    assert "!.env.example" in ignore
