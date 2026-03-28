"""CloakBrowserMCP Server — MCP server exposing CloakBrowser to AI agents.

Registers all tools with the MCP framework and manages the browser session.
Optimized for AI agent consumption: snapshot-based navigation with ref IDs,
text-first content, file-based artifacts, structured page inspection,
and high-level action helpers.
"""

from __future__ import annotations

import json
import logging
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
    # Agent-friendly handlers
    handle_get_text,
    handle_get_links,
    handle_get_form_fields,
    handle_smart_action,
    # New snapshot-based navigation
    handle_snapshot,
    handle_click_ref,
    handle_type_ref,
    handle_get_console,
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
)

logger = logging.getLogger("cloakbrowsermcp")

# ---------------------------------------------------------------------------
# Global session — shared across all tool calls in a single server instance
# ---------------------------------------------------------------------------
_session = BrowserSession()


def _error(message: str) -> str:
    """Return a JSON error string for tool responses."""
    return json.dumps({"error": message})


async def _safe_call(handler, *args, **kwargs) -> str:
    """Call a tool handler with error handling, returning JSON."""
    try:
        result = await handler(*args, **kwargs)
        return json.dumps(result)
    except KeyError as e:
        return _error(f"Page not found: {e}")
    except RuntimeError as e:
        return _error(str(e))
    except Exception as e:
        logger.exception("Tool error in %s", handler.__name__)
        return _error(f"{type(e).__name__}: {e}")


def create_server() -> FastMCP:
    """Create and configure the CloakBrowserMCP server with all tools registered."""

    mcp = FastMCP(
        "cloakbrowser",
        instructions=(
            "Stealth browser automation via CloakBrowser — a source-level patched Chromium "
            "that passes every bot detection test. Optimized for AI agent workflows.\n\n"
            "QUICK START:\n"
            "1. launch_browser() — starts browser, returns a page_id\n"
            "2. navigate(page_id, url) — go to a URL\n"
            "3. snapshot(page_id) — get interactive elements with [@eN] ref IDs\n"
            "4. click_ref(page_id, '@e5') — click element by ref ID from snapshot\n"
            "5. type_ref(page_id, '@e3', 'hello') — type into input by ref ID\n"
            "6. get_text(page_id) — read page content as clean text\n\n"
            "SNAPSHOT WORKFLOW (recommended):\n"
            "The snapshot() tool returns an accessibility-tree-like view of the page.\n"
            "Each interactive element gets a ref ID like [@e1], [@e2], etc.\n"
            "Use click_ref() and type_ref() to interact using these refs.\n"
            "This is much more reliable than CSS selectors for agent workflows.\n\n"
            "TIPS:\n"
            "- Use snapshot() as your primary way to understand page structure\n"
            "- Use get_text() for reading content, snapshot() for interaction\n"
            "- Use smart_action() to click buttons/links by their visible text\n"
            "- Screenshots save to ~/.cloakbrowser/artifacts/ — use vision tools to analyze them\n"
            "- Use get_console() to check for JavaScript errors\n"
            "- Always close_browser() when done to free resources"
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
        return await _safe_call(handle_launch_browser, _session, params)

    @mcp.tool()
    async def close_browser() -> str:
        """Close the stealth browser and all open pages. Always call this when done."""
        return await _safe_call(handle_close_browser, _session, {})

    # -----------------------------------------------------------------------
    # Page management
    # -----------------------------------------------------------------------

    @mcp.tool()
    async def new_page(url: str | None = None) -> str:
        """Open a new browser page/tab, optionally navigating to a URL.

        Args:
            url: URL to navigate to after creating the page.
        """
        return await _safe_call(handle_new_page, _session, {"url": url} if url else {})

    @mcp.tool()
    async def close_page(page_id: str) -> str:
        """Close a specific browser page.

        Args:
            page_id: The page ID returned by launch_browser or new_page.
        """
        return await _safe_call(handle_close_page, _session, {"page_id": page_id})

    @mcp.tool()
    async def list_pages() -> str:
        """List all open browser pages with their IDs and URLs."""
        return await _safe_call(handle_list_pages, _session, {})

    # -----------------------------------------------------------------------
    # Snapshot — the primary way agents understand page structure
    # -----------------------------------------------------------------------

    @mcp.tool()
    async def snapshot(
        page_id: str,
        full: bool = False,
        max_length: int = 8000,
    ) -> str:
        """Get a text snapshot of the page's interactive elements with ref IDs.

        Returns an accessibility-tree-like view where each interactive element
        (links, buttons, inputs, etc.) gets a [@eN] ref ID. Use these refs with
        click_ref() and type_ref() to interact with the page.

        full=False (default): shows only interactive elements — compact and fast.
        full=True: includes text content too — useful for reading page structure.

        This is the PRIMARY tool for understanding what's on the page and deciding
        what to click or type. Always call this before interacting with a page.

        Args:
            page_id: Target page ID.
            full: If true, include text content alongside interactive elements.
            max_length: Max characters to return (default: 8000).
        """
        return await _safe_call(handle_snapshot, _session, {
            "page_id": page_id,
            "full": full,
            "max_length": max_length,
        })

    @mcp.tool()
    async def click_ref(
        page_id: str,
        ref: str,
    ) -> str:
        """Click an element by its [@eN] ref ID from a snapshot.

        Much more reliable than CSS selectors. Call snapshot() first to get ref IDs,
        then click_ref(page_id, '@e5') to click the element.

        Args:
            page_id: Target page ID.
            ref: The ref ID from the snapshot (e.g. '@e5' or 'e5').
        """
        return await _safe_call(handle_click_ref, _session, {
            "page_id": page_id,
            "ref": ref,
        })

    @mcp.tool()
    async def type_ref(
        page_id: str,
        ref: str,
        text: str,
        clear: bool = True,
        delay: int = 0,
    ) -> str:
        """Type text into an input element by its [@eN] ref ID from a snapshot.

        Call snapshot() first to find input fields and their ref IDs.
        Clears the field first by default, then types the text with per-key events.

        Args:
            page_id: Target page ID.
            ref: The ref ID from the snapshot (e.g. '@e3' or 'e3').
            text: The text to type.
            clear: Clear the field before typing (default: True).
            delay: Delay between keystrokes in ms (0=instant, 50-100=realistic).
        """
        return await _safe_call(handle_type_ref, _session, {
            "page_id": page_id,
            "ref": ref,
            "text": text,
            "clear": clear,
            "delay": delay,
        })

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
        return await _safe_call(handle_navigate, _session, {
            "page_id": page_id,
            "url": url,
            "wait_until": wait_until,
            "timeout": timeout,
        })

    @mcp.tool()
    async def go_back(page_id: str) -> str:
        """Navigate back in page history.

        Args:
            page_id: Target page ID.
        """
        return await _safe_call(handle_go_back, _session, {"page_id": page_id})

    @mcp.tool()
    async def go_forward(page_id: str) -> str:
        """Navigate forward in page history.

        Args:
            page_id: Target page ID.
        """
        return await _safe_call(handle_go_forward, _session, {"page_id": page_id})

    @mcp.tool()
    async def reload(page_id: str) -> str:
        """Reload the current page.

        Args:
            page_id: Target page ID.
        """
        return await _safe_call(handle_reload, _session, {"page_id": page_id})

    @mcp.tool()
    async def wait_for_navigation(
        page_id: str,
        state: str = "domcontentloaded",
        timeout: int = 30000,
    ) -> str:
        """Wait for the page to reach a specific load state after a click or action.

        Args:
            page_id: Target page ID.
            state: Load state — 'domcontentloaded', 'load', 'networkidle'.
            timeout: Max wait time in milliseconds.
        """
        return await _safe_call(handle_wait_for_navigation, _session, {
            "page_id": page_id,
            "state": state,
            "timeout": timeout,
        })

    # -----------------------------------------------------------------------
    # Interaction (CSS selector-based — prefer snapshot refs instead)
    # -----------------------------------------------------------------------

    @mcp.tool()
    async def click(
        page_id: str,
        selector: str,
        timeout: int = 5000,
    ) -> str:
        """Click an element using a CSS selector. Prefer click_ref() with snapshot refs instead.

        Args:
            page_id: Target page ID.
            selector: CSS selector of the element to click.
            timeout: Max time to wait for the element in ms.
        """
        return await _safe_call(handle_click, _session, {
            "page_id": page_id,
            "selector": selector,
            "timeout": timeout,
        })

    @mcp.tool()
    async def smart_action(
        page_id: str,
        text: str,
        action: str = "click",
        value: str = "",
    ) -> str:
        """Click a link or button by its visible text — no CSS selector needed.

        Tries multiple strategies (exact text, partial text, ARIA roles, labels,
        placeholders, titles) to find the element. Falls back gracefully with hints.

        Args:
            page_id: Target page ID.
            text: Visible text of the element (e.g. 'Sign In', 'Submit', 'Next').
            action: What to do — 'click', 'fill', or 'type'.
            value: Value to fill/type (only used with action='fill' or 'type').
        """
        return await _safe_call(handle_smart_action, _session, {
            "page_id": page_id,
            "text": text,
            "action": action,
            "value": value,
        })

    @mcp.tool()
    async def type_text(
        page_id: str,
        selector: str,
        text: str,
        delay: int = 0,
    ) -> str:
        """Type text into an element with per-key events. Prefer type_ref() with snapshot refs.

        Better for reCAPTCHA sites than fill_form() because it fires keyboard events.

        Args:
            page_id: Target page ID.
            selector: CSS selector of the input element.
            text: Text to type.
            delay: Delay between keystrokes in ms (0 for instant, 50-100 for realistic).
        """
        return await _safe_call(handle_type_text, _session, {
            "page_id": page_id,
            "selector": selector,
            "text": text,
            "delay": delay,
        })

    @mcp.tool()
    async def fill_form(
        page_id: str,
        selector: str,
        value: str,
    ) -> str:
        """Fill a form field directly (sets value without key events).

        Note: For sites with reCAPTCHA, prefer type_text() or type_ref() which fire keyboard events.

        Args:
            page_id: Target page ID.
            selector: CSS selector of the input element.
            value: Value to fill.
        """
        return await _safe_call(handle_fill_form, _session, {
            "page_id": page_id,
            "selector": selector,
            "value": value,
        })

    @mcp.tool()
    async def hover(page_id: str, selector: str) -> str:
        """Hover over an element. With humanize=True, uses realistic mouse curves.

        Args:
            page_id: Target page ID.
            selector: CSS selector of the element to hover.
        """
        return await _safe_call(handle_hover, _session, {
            "page_id": page_id,
            "selector": selector,
        })

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

        return await _safe_call(handle_select_option, _session, params)

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

        return await _safe_call(handle_press_key, _session, params)

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
        return await _safe_call(handle_scroll, _session, {
            "page_id": page_id,
            "direction": direction,
            "amount": amount,
        })

    # -----------------------------------------------------------------------
    # Content extraction (agent-optimized)
    # -----------------------------------------------------------------------

    @mcp.tool()
    async def get_text(
        page_id: str,
        selector: str = "body",
        max_length: int = 50000,
    ) -> str:
        """Get readable text content from the page — clean, no HTML tags.

        This is the PRIMARY way to read page content. Returns visible text only,
        with whitespace cleaned up. Much better than get_content() for agents.

        Args:
            page_id: Target page ID.
            selector: CSS selector to extract text from (default: 'body' = whole page).
            max_length: Max characters to return (default: 50000). Truncates with notice.
        """
        return await _safe_call(handle_get_text, _session, {
            "page_id": page_id,
            "selector": selector,
            "max_length": max_length,
        })

    @mcp.tool()
    async def get_links(
        page_id: str,
        selector: str = "body",
    ) -> str:
        """Get all visible links from the page with their text and URLs.

        Returns a structured list of links the agent can use for navigation decisions.

        Args:
            page_id: Target page ID.
            selector: CSS selector to scope the search (default: entire page).
        """
        return await _safe_call(handle_get_links, _session, {
            "page_id": page_id,
            "selector": selector,
        })

    @mcp.tool()
    async def get_form_fields(
        page_id: str,
        selector: str = "body",
    ) -> str:
        """Discover all form inputs on the page — types, names, labels, selectors.

        Returns structured data about every visible input, textarea, select, and submit
        button. Each field includes a ready-to-use CSS selector for fill_form()/type_text().

        Args:
            page_id: Target page ID.
            selector: CSS selector to scope the search (default: entire page).
        """
        return await _safe_call(handle_get_form_fields, _session, {
            "page_id": page_id,
            "selector": selector,
        })

    @mcp.tool()
    async def screenshot(
        page_id: str,
        full_page: bool = False,
        selector: str | None = None,
    ) -> str:
        """Take a screenshot — saves PNG to disk and returns the file path.

        Use vision/image analysis tools on the returned path to understand visual content.

        Args:
            page_id: Target page ID.
            full_page: Capture the entire scrollable page.
            selector: CSS selector to screenshot a specific element.
        """
        return await _safe_call(handle_screenshot, _session, {
            "page_id": page_id,
            "full_page": full_page,
            "selector": selector,
        })

    @mcp.tool()
    async def get_content(
        page_id: str,
        selector: str | None = None,
        content_type: str = "html",
    ) -> str:
        """Get raw page content — HTML, text of a selector, or outer HTML.

        NOTE: Prefer get_text() for readable content. This returns raw HTML which
        can be very large. Use this only when you need actual HTML structure.

        Args:
            page_id: Target page ID.
            selector: CSS selector to extract content from. None = full page.
            content_type: 'html' (full page or inner HTML), 'text' (visible text), 'outer_html'.
        """
        return await _safe_call(handle_get_content, _session, {
            "page_id": page_id,
            "selector": selector,
            "content_type": content_type,
        })

    @mcp.tool()
    async def evaluate(page_id: str, expression: str) -> str:
        """Execute JavaScript in the page context and return the result.

        Args:
            page_id: Target page ID.
            expression: JavaScript expression to evaluate.
        """
        return await _safe_call(handle_evaluate, _session, {
            "page_id": page_id,
            "expression": expression,
        })

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
        return await _safe_call(handle_wait_for_selector, _session, {
            "page_id": page_id,
            "selector": selector,
            "state": state,
            "timeout": timeout,
        })

    # -----------------------------------------------------------------------
    # Console output
    # -----------------------------------------------------------------------

    @mcp.tool()
    async def get_console(
        page_id: str,
        clear: bool = False,
    ) -> str:
        """Get browser console output and JavaScript errors from the page.

        Returns console.log/warn/error/info messages and uncaught JS exceptions.
        Useful for detecting silent JavaScript errors, failed API calls, and application warnings.

        Args:
            page_id: Target page ID.
            clear: If true, clear the message buffer after reading.
        """
        return await _safe_call(handle_get_console, _session, {
            "page_id": page_id,
            "clear": clear,
        })

    # -----------------------------------------------------------------------
    # Cookies
    # -----------------------------------------------------------------------

    @mcp.tool()
    async def get_cookies(page_id: str) -> str:
        """Get all cookies from the page's browser context.

        Args:
            page_id: Target page ID.
        """
        return await _safe_call(handle_get_cookies, _session, {"page_id": page_id})

    @mcp.tool()
    async def set_cookies(page_id: str, cookies: list[dict]) -> str:
        """Set cookies in the page's browser context.

        Args:
            page_id: Target page ID.
            cookies: List of cookie dicts with name, value, domain, path fields.
        """
        return await _safe_call(handle_set_cookies, _session, {
            "page_id": page_id,
            "cookies": cookies,
        })

    # -----------------------------------------------------------------------
    # Page info & export
    # -----------------------------------------------------------------------

    @mcp.tool()
    async def get_page_info(page_id: str) -> str:
        """Get current page URL and title.

        Args:
            page_id: Target page ID.
        """
        return await _safe_call(handle_get_page_info, _session, {"page_id": page_id})

    @mcp.tool()
    async def pdf(
        page_id: str,
        format: str = "A4",
        print_background: bool = True,
    ) -> str:
        """Generate a PDF of the current page — saves to disk and returns file path.

        Args:
            page_id: Target page ID.
            format: Page format — 'A4', 'Letter', 'Legal'.
            print_background: Include background graphics.
        """
        return await _safe_call(handle_pdf, _session, {
            "page_id": page_id,
            "format": format,
            "print_background": print_background,
        })

    # -----------------------------------------------------------------------
    # Viewport & media
    # -----------------------------------------------------------------------

    @mcp.tool()
    async def set_viewport(
        page_id: str,
        width: int,
        height: int,
    ) -> str:
        """Set the viewport size of a page.

        Args:
            page_id: Target page ID.
            width: Viewport width in pixels.
            height: Viewport height in pixels.
        """
        return await _safe_call(handle_set_viewport, _session, {
            "page_id": page_id,
            "width": width,
            "height": height,
        })

    @mcp.tool()
    async def emulate_media(
        page_id: str,
        color_scheme: str | None = None,
        media: str | None = None,
        reduced_motion: str | None = None,
    ) -> str:
        """Emulate media features (color scheme, media type, etc.).

        Args:
            page_id: Target page ID.
            color_scheme: 'light', 'dark', or 'no-preference'.
            media: 'screen' or 'print'.
            reduced_motion: 'reduce' or 'no-preference'.
        """
        params: dict[str, Any] = {"page_id": page_id}
        if color_scheme is not None:
            params["color_scheme"] = color_scheme
        if media is not None:
            params["media"] = media
        if reduced_motion is not None:
            params["reduced_motion"] = reduced_motion
        return await _safe_call(handle_emulate_media, _session, params)

    # -----------------------------------------------------------------------
    # Network interception
    # -----------------------------------------------------------------------

    @mcp.tool()
    async def network_intercept(
        page_id: str,
        url_pattern: str,
        action: str = "block",
        mock_body: str = "",
        mock_status: int = 200,
        mock_content_type: str = "application/json",
    ) -> str:
        """Set up network request interception — block, mock, or log requests.

        Useful for blocking ads/trackers, mocking API responses, or testing.

        Args:
            page_id: Target page ID.
            url_pattern: URL pattern to intercept (glob, e.g. '**/api/**' or '**/*.png').
            action: 'block' (abort request), 'mock' (return fake response), 'continue' (passthrough).
            mock_body: Response body when action='mock'.
            mock_status: HTTP status code when action='mock'.
            mock_content_type: Content-Type header when action='mock'.
        """
        return await _safe_call(handle_network_intercept, _session, {
            "page_id": page_id,
            "url_pattern": url_pattern,
            "action": action,
            "mock_body": mock_body,
            "mock_status": mock_status,
            "mock_content_type": mock_content_type,
        })

    @mcp.tool()
    async def network_continue(
        page_id: str,
        url_pattern: str,
    ) -> str:
        """Remove a previously set network interception route.

        Args:
            page_id: Target page ID.
            url_pattern: The same URL pattern used in network_intercept().
        """
        return await _safe_call(handle_network_continue, _session, {
            "page_id": page_id,
            "url_pattern": url_pattern,
        })

    # -----------------------------------------------------------------------
    # Page scripting
    # -----------------------------------------------------------------------

    @mcp.tool()
    async def add_init_script(
        page_id: str,
        script: str,
    ) -> str:
        """Add a JavaScript init script that runs before every page load.

        Useful for injecting polyfills, overriding APIs, or setting up monitoring.

        Args:
            page_id: Target page ID.
            script: JavaScript code to run before page scripts.
        """
        return await _safe_call(handle_add_init_script, _session, {
            "page_id": page_id,
            "script": script,
        })

    # -----------------------------------------------------------------------
    # Stealth inspection
    # -----------------------------------------------------------------------

    @mcp.tool()
    async def stealth_config() -> str:
        """Show the current default CloakBrowser stealth configuration and args."""
        return await _safe_call(handle_stealth_config, {})

    @mcp.tool()
    async def binary_info() -> str:
        """Get info about the CloakBrowser binary (version, path, features)."""
        return await _safe_call(handle_get_binary_info, {})

    # -----------------------------------------------------------------------
    # MCP Prompts — common agent workflows
    # -----------------------------------------------------------------------

    @mcp.prompt()
    def browse_and_extract(url: str, what: str = "main content") -> str:
        """Browse a URL and extract specific content.

        Args:
            url: The URL to visit.
            what: What to extract (e.g. 'main article text', 'all product prices', 'contact info').
        """
        return (
            f"Use CloakBrowser to visit {url} and extract: {what}\n\n"
            "Steps:\n"
            "1. launch_browser()\n"
            "2. navigate(page_id, url)\n"
            "3. snapshot(page_id) to see page structure\n"
            "4. get_text(page_id) to read the content\n"
            "5. If needed, get_links(page_id) to find sub-pages\n"
            "6. Extract the requested information\n"
            "7. close_browser()\n"
        )

    @mcp.prompt()
    def fill_and_submit_form(url: str, instructions: str = "") -> str:
        """Navigate to a page, fill out a form, and submit it.

        Args:
            url: The URL with the form.
            instructions: What to fill in and any specific values.
        """
        return (
            f"Use CloakBrowser to fill and submit a form at {url}\n"
            f"Instructions: {instructions}\n\n"
            "Steps:\n"
            "1. launch_browser(humanize=True) — use humanize for form sites\n"
            "2. navigate(page_id, url)\n"
            "3. snapshot(page_id) to see all form fields with ref IDs\n"
            "4. For each field, use type_ref() to fill it in\n"
            "5. screenshot(page_id) before submitting to verify\n"
            "6. click_ref() on the submit button, or smart_action(page_id, 'Submit')\n"
            "7. wait_for_navigation(page_id) to confirm submission\n"
            "8. get_text(page_id) to read the result\n"
            "9. close_browser()\n"
        )

    @mcp.prompt()
    def login_to_site(url: str, username: str = "", password: str = "") -> str:
        """Log into a website with credentials.

        Args:
            url: Login page URL.
            username: Username/email to use.
            password: Password to use.
        """
        return (
            f"Use CloakBrowser to log into {url}\n\n"
            "Steps:\n"
            "1. launch_browser(humanize=True) — humanize helps avoid detection\n"
            "2. navigate(page_id, url)\n"
            "3. snapshot(page_id) to find username/password fields\n"
            f"4. type_ref() the username field: {username or '[ask user]'}\n"
            f"5. type_ref() the password field: {password or '[ask user]'}\n"
            "6. click_ref() on the sign-in button, or smart_action(page_id, 'Sign In')\n"
            "7. wait_for_navigation(page_id, state='networkidle')\n"
            "8. snapshot(page_id) to verify login succeeded\n"
            "9. Keep browser open for further actions\n"
        )

    @mcp.prompt()
    def scrape_multiple_pages(start_url: str, pattern: str = "") -> str:
        """Scrape data from multiple pages (pagination, search results, etc.).

        Args:
            start_url: Starting URL.
            pattern: What data to collect from each page.
        """
        return (
            f"Use CloakBrowser to scrape multiple pages starting at {start_url}\n"
            f"Data to collect: {pattern or 'all main content'}\n\n"
            "Steps:\n"
            "1. launch_browser()\n"
            "2. navigate(page_id, start_url)\n"
            "3. get_text(page_id) — extract data from current page\n"
            "4. snapshot(page_id) — find 'Next' or pagination links\n"
            "5. Loop: click_ref() on next page, extract data, find next link\n"
            "6. Collect all data and present it\n"
            "7. close_browser()\n"
        )

    return mcp


def main():
    """Entry point for the CloakBrowserMCP server."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    server = create_server()
    server.run()


if __name__ == "__main__":
    main()
