"""CloakBrowserMCP Server — MCP server exposing CloakBrowser to AI models.

Registers all tools with the MCP framework and manages the browser session.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import FastMCP

from .session import BrowserSession
from .tools import (
    handle_launch_browser,
    handle_close_browser,
    handle_new_page,
    handle_close_page,
    handle_list_pages,
    handle_navigate,
    handle_click,
    handle_type_text,
    handle_fill_form,
    handle_screenshot,
    handle_get_content,
    handle_evaluate,
    handle_wait_for_selector,
    handle_hover,
    handle_select_option,
    handle_press_key,
    handle_scroll,
    handle_get_cookies,
    handle_set_cookies,
    handle_get_page_info,
    handle_pdf,
)
from .tools_advanced import (
    handle_stealth_config,
    handle_get_binary_info,
    handle_network_intercept,
    handle_network_continue,
    handle_wait_for_navigation,
    handle_go_back,
    handle_go_forward,
    handle_reload,
    handle_set_viewport,
    handle_emulate_media,
    handle_add_init_script,
    handle_expose_function,
)

logger = logging.getLogger("cloakbrowsermcp")

# ---------------------------------------------------------------------------
# Global session — shared across all tool calls in a single server instance
# ---------------------------------------------------------------------------
_session = BrowserSession()


def create_server() -> FastMCP:
    """Create and configure the CloakBrowserMCP server with all tools registered."""

    mcp = FastMCP(
        "CloakBrowserMCP",
        instructions=(
            "Stealth browser automation via CloakBrowser — a source-level patched Chromium "
            "that passes every bot detection test. Provides full Playwright-compatible browser "
            "control with anti-detection stealth built in. Always launch_browser first, then "
            "use the returned page_id for all subsequent operations."
        ),
    )

    # -----------------------------------------------------------------------
    # Browser lifecycle
    # -----------------------------------------------------------------------

    @mcp.tool()
    async def launch_browser(
        headless: bool = True,
        proxy: str | None = None,
        humanize: bool = False,
        human_preset: str = "default",
        stealth_args: bool = True,
        timezone: str | None = None,
        locale: str | None = None,
        geoip: bool = False,
        fingerprint_seed: str | None = None,
        user_data_dir: str | None = None,
        viewport_width: int = 1920,
        viewport_height: int = 947,
        color_scheme: str | None = None,
        user_agent: str | None = None,
        extra_args: list[str] | None = None,
    ) -> str:
        """Launch a stealth CloakBrowser instance with anti-detection.

        CloakBrowser is a source-level patched Chromium that passes Cloudflare Turnstile,
        reCAPTCHA v3 (0.9 score), FingerprintJS, BrowserScan, and 30+ detection services.

        Args:
            headless: Run in headless mode. Some aggressive sites require headed mode.
            proxy: Proxy URL (e.g. 'http://user:pass@proxy:8080'). Residential proxies recommended.
            humanize: Enable human-like mouse curves, keyboard timing, scroll patterns.
            human_preset: 'default' or 'careful' (slower, more deliberate movements).
            stealth_args: Include default stealth fingerprint args (disable to set custom flags).
            timezone: IANA timezone (e.g. 'America/New_York') — set via binary flag, not CDP.
            locale: BCP 47 locale (e.g. 'en-US').
            geoip: Auto-detect timezone/locale from proxy IP.
            fingerprint_seed: Fixed seed for consistent identity across sessions.
            user_data_dir: Path for persistent profile (cookies/localStorage survive restarts).
            viewport_width: Browser viewport width.
            viewport_height: Browser viewport height.
            color_scheme: Color scheme — 'light', 'dark', or 'no-preference'.
            user_agent: Custom user agent string.
            extra_args: Additional Chromium CLI arguments.
        """
        params = {
            "headless": headless,
            "proxy": proxy,
            "humanize": humanize,
            "human_preset": human_preset,
            "stealth_args": stealth_args,
            "timezone": timezone,
            "locale": locale,
            "geoip": geoip,
            "fingerprint_seed": fingerprint_seed,
            "user_data_dir": user_data_dir,
            "viewport": {"width": viewport_width, "height": viewport_height},
            "color_scheme": color_scheme,
            "user_agent": user_agent,
            "extra_args": extra_args or [],
        }
        result = await handle_launch_browser(_session, params)
        return json.dumps(result)

    @mcp.tool()
    async def close_browser() -> str:
        """Close the stealth browser and all open pages."""
        result = await handle_close_browser(_session, {})
        return json.dumps(result)

    # -----------------------------------------------------------------------
    # Page management
    # -----------------------------------------------------------------------

    @mcp.tool()
    async def new_page(url: str | None = None) -> str:
        """Open a new browser page/tab, optionally navigating to a URL.

        Args:
            url: URL to navigate to after creating the page.
        """
        result = await handle_new_page(_session, {"url": url} if url else {})
        return json.dumps(result)

    @mcp.tool()
    async def close_page(page_id: str) -> str:
        """Close a specific browser page.

        Args:
            page_id: The page ID returned by launch_browser or new_page.
        """
        result = await handle_close_page(_session, {"page_id": page_id})
        return json.dumps(result)

    @mcp.tool()
    async def list_pages() -> str:
        """List all open browser pages with their IDs and URLs."""
        result = await handle_list_pages(_session, {})
        return json.dumps(result)

    # -----------------------------------------------------------------------
    # Navigation
    # -----------------------------------------------------------------------

    @mcp.tool()
    async def navigate(
        page_id: str,
        url: str,
        wait_until: str = "domcontentloaded",
        timeout: int = 30000,
    ) -> str:
        """Navigate a page to a URL.

        Args:
            page_id: Target page ID.
            url: URL to navigate to.
            wait_until: When to consider navigation done — 'domcontentloaded', 'load', 'networkidle'.
            timeout: Navigation timeout in milliseconds.
        """
        result = await handle_navigate(_session, {
            "page_id": page_id,
            "url": url,
            "wait_until": wait_until,
            "timeout": timeout,
        })
        return json.dumps(result)

    # -----------------------------------------------------------------------
    # Interaction
    # -----------------------------------------------------------------------

    @mcp.tool()
    async def click(
        page_id: str,
        selector: str,
        timeout: int = 5000,
    ) -> str:
        """Click an element on the page. With humanize=True, uses Bézier mouse curves.

        Args:
            page_id: Target page ID.
            selector: CSS selector of the element to click.
            timeout: Max time to wait for the element in ms.
        """
        result = await handle_click(_session, {
            "page_id": page_id,
            "selector": selector,
            "timeout": timeout,
        })
        return json.dumps(result)

    @mcp.tool()
    async def type_text(
        page_id: str,
        selector: str,
        text: str,
        delay: int = 0,
    ) -> str:
        """Type text into an element with per-key events. Better for reCAPTCHA than fill().

        Args:
            page_id: Target page ID.
            selector: CSS selector of the input element.
            text: Text to type.
            delay: Delay between keystrokes in ms (0 for instant, 50-100 for realistic).
        """
        result = await handle_type_text(_session, {
            "page_id": page_id,
            "selector": selector,
            "text": text,
            "delay": delay,
        })
        return json.dumps(result)

    @mcp.tool()
    async def fill_form(
        page_id: str,
        selector: str,
        value: str,
    ) -> str:
        """Fill a form field directly (sets value without key events).

        Note: For sites with reCAPTCHA, prefer type_text() which fires keyboard events.

        Args:
            page_id: Target page ID.
            selector: CSS selector of the input element.
            value: Value to fill.
        """
        result = await handle_fill_form(_session, {
            "page_id": page_id,
            "selector": selector,
            "value": value,
        })
        return json.dumps(result)

    @mcp.tool()
    async def hover(page_id: str, selector: str) -> str:
        """Hover over an element. With humanize=True, uses realistic mouse curves.

        Args:
            page_id: Target page ID.
            selector: CSS selector of the element to hover.
        """
        result = await handle_hover(_session, {
            "page_id": page_id,
            "selector": selector,
        })
        return json.dumps(result)

    @mcp.tool()
    async def select_option(
        page_id: str,
        selector: str,
        value: str | None = None,
        label: str | None = None,
        index: int | None = None,
    ) -> str:
        """Select an option from a <select> dropdown.

        Args:
            page_id: Target page ID.
            selector: CSS selector of the <select> element.
            value: Option value to select.
            label: Option visible text to select.
            index: Option index to select (0-based).
        """
        params: dict[str, Any] = {"page_id": page_id, "selector": selector}
        if value is not None:
            params["value"] = value
        if label is not None:
            params["label"] = label
        if index is not None:
            params["index"] = index

        result = await handle_select_option(_session, params)
        return json.dumps(result)

    @mcp.tool()
    async def press_key(
        page_id: str,
        key: str,
        selector: str | None = None,
    ) -> str:
        """Press a keyboard key (e.g. Enter, Tab, Escape, ArrowDown).

        Args:
            page_id: Target page ID.
            key: Key to press (DOM KeyboardEvent key name).
            selector: Optional element to focus before pressing.
        """
        params: dict[str, Any] = {"page_id": page_id, "key": key}
        if selector:
            params["selector"] = selector

        result = await handle_press_key(_session, params)
        return json.dumps(result)

    @mcp.tool()
    async def scroll(
        page_id: str,
        direction: str = "down",
        amount: int = 300,
    ) -> str:
        """Scroll the page. With humanize=True, uses realistic acceleration curves.

        Args:
            page_id: Target page ID.
            direction: 'up' or 'down'.
            amount: Pixels to scroll.
        """
        result = await handle_scroll(_session, {
            "page_id": page_id,
            "direction": direction,
            "amount": amount,
        })
        return json.dumps(result)

    # -----------------------------------------------------------------------
    # Content extraction
    # -----------------------------------------------------------------------

    @mcp.tool()
    async def screenshot(
        page_id: str,
        full_page: bool = False,
        selector: str | None = None,
    ) -> str:
        """Take a screenshot of the page or a specific element.

        Args:
            page_id: Target page ID.
            full_page: Capture the entire scrollable page.
            selector: CSS selector to screenshot a specific element.
        """
        result = await handle_screenshot(_session, {
            "page_id": page_id,
            "full_page": full_page,
            "selector": selector,
        })
        return json.dumps(result)

    @mcp.tool()
    async def get_content(
        page_id: str,
        selector: str | None = None,
        content_type: str = "html",
    ) -> str:
        """Get page content — full HTML, text of a selector, or outer HTML.

        Args:
            page_id: Target page ID.
            selector: CSS selector to extract content from. None = full page.
            content_type: 'html' (full page or inner HTML), 'text' (visible text), 'outer_html'.
        """
        result = await handle_get_content(_session, {
            "page_id": page_id,
            "selector": selector,
            "content_type": content_type,
        })
        return json.dumps(result)

    @mcp.tool()
    async def evaluate(page_id: str, expression: str) -> str:
        """Execute JavaScript in the page context and return the result.

        Args:
            page_id: Target page ID.
            expression: JavaScript expression to evaluate.
        """
        result = await handle_evaluate(_session, {
            "page_id": page_id,
            "expression": expression,
        })
        return json.dumps(result)

    @mcp.tool()
    async def wait_for_selector(
        page_id: str,
        selector: str,
        state: str = "visible",
        timeout: int = 30000,
    ) -> str:
        """Wait for an element to reach a state (visible, hidden, attached, detached).

        Args:
            page_id: Target page ID.
            selector: CSS selector to wait for.
            state: Target state — 'visible', 'hidden', 'attached', 'detached'.
            timeout: Max wait time in milliseconds.
        """
        result = await handle_wait_for_selector(_session, {
            "page_id": page_id,
            "selector": selector,
            "state": state,
            "timeout": timeout,
        })
        return json.dumps(result)

    # -----------------------------------------------------------------------
    # Cookies
    # -----------------------------------------------------------------------

    @mcp.tool()
    async def get_cookies(page_id: str) -> str:
        """Get all cookies from the page's browser context.

        Args:
            page_id: Target page ID.
        """
        result = await handle_get_cookies(_session, {"page_id": page_id})
        return json.dumps(result)

    @mcp.tool()
    async def set_cookies(page_id: str, cookies: list[dict]) -> str:
        """Set cookies in the page's browser context.

        Args:
            page_id: Target page ID.
            cookies: List of cookie dicts with name, value, domain, path fields.
        """
        result = await handle_set_cookies(_session, {
            "page_id": page_id,
            "cookies": cookies,
        })
        return json.dumps(result)

    # -----------------------------------------------------------------------
    # Page info & export
    # -----------------------------------------------------------------------

    @mcp.tool()
    async def get_page_info(page_id: str) -> str:
        """Get current page URL and title.

        Args:
            page_id: Target page ID.
        """
        result = await handle_get_page_info(_session, {"page_id": page_id})
        return json.dumps(result)

    @mcp.tool()
    async def pdf(
        page_id: str,
        format: str = "A4",
        print_background: bool = True,
    ) -> str:
        """Generate a PDF of the current page.

        Args:
            page_id: Target page ID.
            format: Page format — 'A4', 'Letter', 'Legal'.
            print_background: Include background graphics.
        """
        result = await handle_pdf(_session, {
            "page_id": page_id,
            "format": format,
            "print_background": print_background,
        })
        return json.dumps(result)

    return mcp


def main():
    """Entry point for the CloakBrowserMCP server."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    server = create_server()
    server.run()


if __name__ == "__main__":
    main()
