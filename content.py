"""Keeps the website static: no scripts, inline event handlers, frames or redirects, whatever the file is called."""

from __future__ import annotations

import re


class ActiveContentError(ValueError):
    pass


_RULES = [
    (re.compile(r"<\s*/?\s*script", re.I), "a <script> tag"),
    (re.compile(r"<\s*(iframe|frame|frameset|object|embed|applet)\b", re.I), "an embedded frame or object"),
    (re.compile(r"""[\s"'/]on[a-z]{3,}\s*=""", re.I), "an inline event handler (onclick=, onload=, ...)"),
    (re.compile(r"(?:java|vb)script\s*:", re.I), "a javascript: link"),
    (re.compile(r"data\s*:\s*text/html", re.I), "a data:text/html link"),
    (re.compile(r"<\s*meta\b[^>]*http-equiv\s*=\s*[\"']?\s*refresh", re.I), "a meta refresh redirect"),
]


def check_static(text: str) -> None:
    """Raise if the text carries anything a browser would run or follow on its own. A filter, not a sandbox."""
    for pattern, what in _RULES:
        if pattern.search(text):
            raise ActiveContentError(
                f"the website is static: {what} is not allowed. Write plain pages; draw with SVG shapes instead of scripts.")
