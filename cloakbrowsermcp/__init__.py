"""CloakBrowserMCP — MCP server exposing CloakBrowser stealth browser automation to AI models."""

__version__ = "0.1.0"

from .session import BrowserSessionError, PageNotFoundError, PageClosedError

__all__ = [
    "BrowserSessionError",
    "PageNotFoundError",
    "PageClosedError",
]
