"""CloakBrowser MCP v2 — Stealth browser automation for AI agents."""

__version__ = "2.0.0"

from .session import BrowserSessionError, PageNotFoundError, PageClosedError

__all__ = [
    "BrowserSessionError",
    "PageNotFoundError",
    "PageClosedError",
]
