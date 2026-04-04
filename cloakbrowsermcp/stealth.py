"""Stealth utilities — exposes CloakBrowser binary info and default stealth args.

Thin wrapper so MCP tools can report what binary/stealth configuration is active
without importing cloakbrowser internals directly.
"""

from __future__ import annotations

from cloakbrowser import binary_info
from cloakbrowser.config import get_default_stealth_args


def get_stealth_info() -> dict:
    """Return a dict with CloakBrowser binary info and default stealth args.

    Useful for diagnostics and for reporting the active stealth configuration
    to the agent.
    """
    info = binary_info()
    return {
        "binary": info,
        "default_stealth_args": get_default_stealth_args(),
    }
