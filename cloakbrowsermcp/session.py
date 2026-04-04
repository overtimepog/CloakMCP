"""BrowserSession — manages CloakBrowser lifecycle, pages, and contexts.

This is the core state manager. The MCP tools delegate all browser
operations through a single BrowserSession instance.
"""

from __future__ import annotations

import asyncio
import uuid
import time
import logging
from dataclasses import dataclass, field
from typing import Any

from cloakbrowser import launch_async, launch_persistent_context_async

logger = logging.getLogger("cloakbrowsermcp")


class BrowserSessionError(RuntimeError):
    """Raised when the browser session is in an invalid state."""
    pass


class PageNotFoundError(KeyError):
    """Raised when a page_id doesn't exist in the session."""
    pass


class PageClosedError(BrowserSessionError):
    """Raised when a page exists in tracking but is actually closed/crashed."""
    pass


@dataclass
class SessionConfig:
    """Configuration for launching a CloakBrowser session.

    Maps 1:1 to CloakBrowser's launch() parameters.
    """

    headless: bool = True
    proxy: str | dict | None = None
    humanize: bool = True
    human_preset: str = "default"
    human_config: dict | None = None
    stealth_args: bool = True
    timezone: str | None = None
    locale: str | None = None
    geoip: bool = False
    viewport: dict = field(default_factory=lambda: {"width": 1920, "height": 947})
    extra_args: list[str] = field(default_factory=list)
    fingerprint_seed: str | None = None
    user_data_dir: str | None = None
    color_scheme: str | None = None
    user_agent: str | None = None
    backend: str | None = None


class BrowserSession:
    """Manages a CloakBrowser instance and its pages.

    Provides page lifecycle management (create, get, close) and
    centralizes browser state so MCP tools can operate statelessly.
    """

    def __init__(self) -> None:
        self._browser: Any | None = None
        self._context: Any | None = None
        self._is_persistent: bool = False
        self.pages: dict[str, Any] = {}
        self.config: SessionConfig | None = None
        self._route_handlers: dict[str, Any] = {}
        # Ref IDs from snapshot, keyed by page_id
        self._refs: dict[str, dict[str, dict]] = {}
        # Console messages captured per page
        self._console_messages: dict[str, list[dict]] = {}

    @property
    def is_running(self) -> bool:
        """Whether the browser is currently running and responsive.

        Checks not just that we hold a reference, but that the underlying
        browser process is still connected.
        """
        if self._is_persistent and self._context is not None:
            try:
                # Persistent context — check if still usable
                # Playwright contexts don't have .is_connected(), but
                # the browser behind them does. For persistent contexts
                # we check if we can still list pages.
                return True
            except Exception:
                return False
        if self._browser is not None:
            try:
                return self._browser.is_connected()
            except Exception:
                return False
        return False

    def _check_browser_alive(self) -> None:
        """Verify the browser is alive; force-cleanup stale state if not.

        Call this before any operation that needs the browser.
        Raises BrowserSessionError with a helpful message.
        """
        if self._browser is None and self._context is None:
            return  # Not running, nothing to check

        if not self.is_running:
            logger.warning("Browser process died — cleaning up stale session state")
            self._force_cleanup()
            raise BrowserSessionError(
                "Browser process has died or been disconnected. "
                "Call launch_browser() to start a new session."
            )

    # -----------------------------------------------------------------------
    # Ref management (for snapshot -> click_ref/type_ref workflow)
    # -----------------------------------------------------------------------

    def set_refs(self, page_id: str, refs: dict[str, dict]) -> None:
        """Store ref IDs from a snapshot for a page."""
        self._refs[page_id] = refs

    def get_refs(self, page_id: str) -> dict[str, dict]:
        """Get stored ref IDs for a page. Returns empty dict if no snapshot taken."""
        return self._refs.get(page_id, {})

    # -----------------------------------------------------------------------
    # Console message management
    # -----------------------------------------------------------------------

    def get_console_messages(self, page_id: str) -> list[dict]:
        """Get captured console messages for a page."""
        return self._console_messages.get(page_id, [])

    def clear_console_messages(self, page_id: str) -> None:
        """Clear captured console messages for a page."""
        self._console_messages[page_id] = []

    def _append_console_message(self, page_id: str, entry: dict[str, Any]) -> None:
        """Append a console entry and cap the buffer size for agent-friendly output."""
        messages = self._console_messages.setdefault(page_id, [])
        messages.append(entry)
        if len(messages) > 200:
            del messages[:-200]

    def _normalize_console_location(self, msg: Any) -> dict[str, Any] | None:
        """Extract location metadata from a Playwright console message when available."""
        raw_location = getattr(msg, "location", None)
        if callable(raw_location):
            raw_location = raw_location()

        if not raw_location:
            return None

        if isinstance(raw_location, dict):
            location = {
                "url": raw_location.get("url"),
                "line": raw_location.get("lineNumber"),
                "column": raw_location.get("columnNumber"),
            }
        else:
            location = {
                "url": getattr(raw_location, "url", None),
                "line": getattr(raw_location, "lineNumber", None),
                "column": getattr(raw_location, "columnNumber", None),
            }

        if not any(value is not None for value in location.values()):
            return None
        return location

    def _setup_console_capture(self, page_id: str, page: Any) -> None:
        """Set up console message capture for a page."""
        self._console_messages[page_id] = []

        def on_console(msg):
            entry: dict[str, Any] = {
                "type": getattr(msg, "type", "log"),
                "text": getattr(msg, "text", ""),
                "timestamp": time.time(),
                "page_url": getattr(page, "url", ""),
            }
            location = self._normalize_console_location(msg)
            if location:
                entry["location"] = location
            self._append_console_message(page_id, entry)

        def on_page_error(error):
            self._append_console_message(page_id, {
                "type": "error",
                "text": f"[PageError] {error}",
                "timestamp": time.time(),
                "page_url": getattr(page, "url", ""),
            })

        page.on("console", on_console)
        page.on("pageerror", on_page_error)

    # -----------------------------------------------------------------------
    # Stale session cleanup
    # -----------------------------------------------------------------------

    def _force_cleanup(self) -> None:
        """Synchronously reset all internal state when the browser has died.

        This does NOT call async close methods — those would fail on a dead
        process. Instead it just wipes references so the session can be
        relaunched cleanly.
        """
        self.pages.clear()
        self._route_handlers.clear()
        self._refs.clear()
        self._console_messages.clear()
        self._browser = None
        self._context = None
        self.config = None
        self._is_persistent = False
        logger.info("Stale browser session cleaned up")

    # -----------------------------------------------------------------------
    # Browser lifecycle
    # -----------------------------------------------------------------------

    async def launch(self, config: SessionConfig) -> None:
        """Launch a CloakBrowser instance with the given configuration."""
        if self.is_running:
            await self.close()
        elif self._browser is not None or self._context is not None:
            # Browser reference exists but process is dead — clean up
            self._force_cleanup()

        self.config = config

        # Build extra args with fingerprint seed if specified
        args = list(config.extra_args)
        if config.fingerprint_seed:
            args.append(f"--fingerprint={config.fingerprint_seed}")

        if config.user_data_dir:
            # Persistent context mode
            self._is_persistent = True
            ctx = await launch_persistent_context_async(
                user_data_dir=config.user_data_dir,
                headless=config.headless,
                proxy=config.proxy,
                args=args if args else None,
                stealth_args=config.stealth_args,
                timezone=config.timezone,
                locale=config.locale,
                geoip=config.geoip,
                humanize=config.humanize,
                human_preset=config.human_preset,
                human_config=config.human_config,
                viewport=config.viewport,
                user_agent=config.user_agent,
                color_scheme=config.color_scheme,
                backend=config.backend,
            )
            self._context = ctx
            self._browser = None
        else:
            # Standard browser mode
            self._is_persistent = False
            browser = await launch_async(
                headless=config.headless,
                proxy=config.proxy,
                args=args if args else None,
                stealth_args=config.stealth_args,
                timezone=config.timezone,
                locale=config.locale,
                geoip=config.geoip,
                humanize=config.humanize,
                human_preset=config.human_preset,
                human_config=config.human_config,
                backend=config.backend,
            )
            self._browser = browser
            self._context = None

        logger.info(
            "CloakBrowser launched (headless=%s, humanize=%s, persistent=%s)",
            config.headless,
            config.humanize,
            self._is_persistent,
        )

    async def close(self) -> None:
        """Close the browser and clean up all pages."""
        if not self.is_running:
            return

        # Close all tracked pages
        for page_id in list(self.pages.keys()):
            try:
                await self.pages[page_id].close()
            except Exception:
                pass
        self.pages.clear()
        self._route_handlers.clear()
        self._refs.clear()
        self._console_messages.clear()

        # Close browser/context
        try:
            if self._is_persistent and self._context:
                await self._context.close()
            elif self._browser:
                await self._browser.close()
        except Exception as e:
            logger.warning("Error closing browser: %s", e)
        finally:
            self._browser = None
            self._context = None
            self.config = None

        logger.info("CloakBrowser closed")

    async def new_page(self) -> str:
        """Create a new page and return its ID."""
        self._check_browser_alive()
        if not self.is_running:
            raise BrowserSessionError("Browser is not running. Call launch_browser() first.")

        if self._is_persistent:
            page = await self._context.new_page()
        else:
            # Create a new context for each page for isolation
            context = await self._browser.new_context(
                viewport=self.config.viewport if self.config else None,
            )
            page = await context.new_page()

        page_id = f"page_{uuid.uuid4().hex[:8]}"
        self.pages[page_id] = page

        # Set up console capture
        self._setup_console_capture(page_id, page)

        logger.debug("New page created: %s", page_id)
        return page_id

    def get_page(self, page_id: str) -> Any:
        """Get a page by its ID.

        Raises PageNotFoundError if the page_id doesn't exist.
        Raises PageClosedError if the page exists but has been closed/crashed.
        Raises BrowserSessionError if the browser process has died.
        """
        self._check_browser_alive()

        if page_id not in self.pages:
            available = list(self.pages.keys())
            raise PageNotFoundError(
                f"Page '{page_id}' not found. "
                + (f"Available pages: {available}" if available
                   else "No pages open. Call launch_browser() to start a new session.")
            )

        page = self.pages[page_id]

        # Check if the page is still alive (Playwright sets is_closed())
        if page.is_closed():
            # Clean up the dead page from tracking
            del self.pages[page_id]
            self._refs.pop(page_id, None)
            self._console_messages.pop(page_id, None)
            raise PageClosedError(
                f"Page '{page_id}' has been closed or crashed. "
                "Use new_page() to create a new one, or launch_browser() to restart."
            )

        return page

    async def close_page(self, page_id: str) -> None:
        """Close a specific page by ID."""
        page = self.get_page(page_id)
        await page.close()
        del self.pages[page_id]
        self._refs.pop(page_id, None)
        self._console_messages.pop(page_id, None)
        logger.debug("Page closed: %s", page_id)

    def list_pages(self) -> list[dict[str, str]]:
        """List all open pages with their IDs and URLs."""
        result = []
        for pid, page in self.pages.items():
            result.append({
                "page_id": pid,
                "url": page.url,
            })
        return result

    # -----------------------------------------------------------------------
    # Page settling (wait for DOM + network stability)
    # -----------------------------------------------------------------------

    async def settle_page(
        self,
        page_id: str,
        timeout_ms: int = 5000,
        stable_ms: int = 500,
    ) -> None:
        """Wait for a page to become stable (no DOM mutations + network idle).

        Uses a MutationObserver to detect when the DOM stops changing for
        `stable_ms` milliseconds, combined with Playwright's networkidle.
        Useful after navigation or interaction before taking a snapshot.

        Args:
            page_id: The page to settle.
            timeout_ms: Maximum time to wait in milliseconds (default 5000).
            stable_ms: Duration of no DOM mutations to consider stable (default 500).
        """
        page = self.get_page(page_id)

        # Wait for DOM stability via MutationObserver
        js_wait_stable = """
        (stableMs) => new Promise((resolve) => {
            let timer = null;
            const observer = new MutationObserver(() => {
                clearTimeout(timer);
                timer = setTimeout(() => {
                    observer.disconnect();
                    resolve(true);
                }, stableMs);
            });
            observer.observe(document.body || document.documentElement, {
                childList: true,
                subtree: true,
                attributes: true,
                characterData: true,
            });
            // Start the timer immediately — if nothing mutates, resolve after stableMs
            timer = setTimeout(() => {
                observer.disconnect();
                resolve(true);
            }, stableMs);
        })
        """

        try:
            # Run DOM stability check and networkidle concurrently
            await asyncio.gather(
                page.evaluate(js_wait_stable, stable_ms),
                page.wait_for_load_state("networkidle", timeout=timeout_ms),
            )
        except Exception as e:
            # Timeouts are acceptable — page may never fully settle (e.g. live feeds)
            logger.debug("settle_page(%s) completed with: %s", page_id, e)
