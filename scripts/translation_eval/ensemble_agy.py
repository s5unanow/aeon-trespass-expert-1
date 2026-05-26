"""AGY CLI helper functions for the S5U-776 ensemble translation POC."""

from __future__ import annotations

import re

AGY_MODEL_PROFILE = "gemini-pro-high"
AGY_DEFAULT_TIMEOUT = "15m"

_DURATION_PART_RE = re.compile(r"(?:(?P<h>\d+)h)?(?:(?P<m>\d+)m)?(?:(?P<s>\d+)s)?$")
_AGY_ERROR_PREFIXES = ("error:", "fatal:")


def build_agy_prompt(system_prompt: str, user_message: str) -> str:
    """Combine the variant system prompt and source text for ``agy --print``."""
    return "\n\n".join(
        [
            system_prompt,
            "AGY model profile requested by the pipeline: Pro model with high effort. "
            "Use that profile if your current Antigravity CLI session supports it.",
            "--- Source text to translate ---",
            user_message.rstrip(),
            "--- Output contract ---",
            "Output only the Russian translation. Do not include commentary.",
        ]
    )


def build_agy_argv(
    *,
    executable: str,
    prompt: str,
    timeout: str,
) -> list[str]:
    """Build the current AGY v1 non-interactive argv.

    Local ``agy --help`` exposes ``--print`` and ``--print-timeout`` but no
    model/effort flags. Keep this isolated so future AGY model-selection flags
    can be added in one place.
    """
    return [executable, "--print-timeout", timeout, "--print", prompt]


def looks_like_agy_error(text: str) -> bool:
    """AGY can report internal failures on stdout while exiting 0."""
    normalized = text.strip().lower()
    return normalized.startswith(_AGY_ERROR_PREFIXES) or "timed out waiting" in normalized


def duration_to_seconds(raw: str) -> int:
    """Parse AGY-style duration strings such as ``15m`` / ``5m0s`` / ``900s``."""
    value = raw.strip().lower()
    if value.isdigit():
        return int(value)
    match = _DURATION_PART_RE.fullmatch(value)
    if not match:
        msg = f"unsupported duration: {raw!r}"
        raise ValueError(msg)
    hours = int(match.group("h") or 0)
    minutes = int(match.group("m") or 0)
    seconds = int(match.group("s") or 0)
    total = hours * 3600 + minutes * 60 + seconds
    if total <= 0:
        msg = f"duration must be positive: {raw!r}"
        raise ValueError(msg)
    return total
