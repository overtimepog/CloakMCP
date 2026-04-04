"""CloakBrowser MCP v2 — Stealth browser automation for AI agents.

A clean, focused MCP server that combines CloakBrowser's anti-detection
with Playwright MCP-inspired architecture: snapshot-first navigation,
ref-based interaction, clean markdown extraction, and annotated screenshots.

~20 core tools. Stealth by default. No CSS selector tools.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .session import (
    BrowserSession,
    BrowserSessionError,
    PageNotFoundError,
    PageClosedError,
    SessionConfig,
)
from .snapshot import take_snapshot, resolve_ref
from .markdown import extract_markdown
from .vision import take_annotated_screenshot
from .waiting import smart_navigate, retry_action, wait_for_settle, detect_loading
from .stealth import get_stealth_info
from .network import (
    setup_intercept,
    remove_intercept,
    get_cookies as _get_cookies,
    set_cookies as _set_cookies,
)

logger = logging.getLogger("cloakbrowsermcp")

LOGS_DIR = Path.home() / ".cloakbrowser" / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Global session — shared across all tool calls in a single server instance
# ---------------------------------------------------------------------------
_session = BrowserSession()

# Capability flags — set via --caps CLI argument
_capabilities: set[str] = set()


def _configure_logging() -> None:
    """Configure logging without polluting stdio MCP traffic."""
    if getattr(_configure_logging, "_done", False):
        return

    log_level = os.getenv("CLOAKBROWSER_LOG_LEVEL", "INFO").upper()
    log_path = Path(os.getenv("CLOAKBROWSER_LOG_FILE", str(LOGS_DIR / "server.log")))
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(log_path)
    fh.setFormatter(formatter)

    logger.handlers.clear()
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    logger.addHandler(fh)
    logger.propagate = False

    if os.getenv("CLOAKBROWSER_LOG_STDERR", "").lower() in {"1", "true", "yes"}:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(formatter)
        logger.addHandler(sh)

    # Silence noisy framework loggers
    for name in ("mcp", "mcp.server", "mcp.server.lowlevel", "mcp.server.fastmcp", "anyio", "uvicorn"):
        logging.getLogger(name).setLevel(logging.ERROR)

    _configure_logging._done = True


# ---------------------------------------------------------------------------
# Error handling helpers
# ---------------------------------------------------------------------------

def _err(msg: str, *, hint: str | None = None) -> dict[str, Any]:
    """Structured error response."""
    r: dict[str, Any] = {"status": "error", "error": msg}
    if hint:
        r["hint"] = hint
    return r


async def _safe(handler, *args, **kwargs) -> dict[str, Any]:
    """Call handler with error handling. Returns structured output."""
    try:
        return await handler(*args, **kwargs)
    except (PageNotFoundError, PageClosedError, BrowserSessionError) as e:
        return _err(str(e))
    except KeyError as e:
        return _err(str(e), hint="Call cloak_snapshot() first to get fresh ref IDs.")
    except Exception as e:
        err_str = str(e).lower()
        if any(kw in err_str for kw in ("closed", "crashed", "disconnected", "not connected")):
            _session._force_cleanup()
            logger.warning("Browser connection lost: %s", e)
            return _err(
                f"Browser session lost. Call cloak_launch() to start a new session.",
                hint="Call cloak_launch() to restart.",
            )
        logger.exception("Tool error: %s", type(e).__name__)
        return _err(f"{type(e).__name__}: {e}")


async def _safe_snap(handler, *args, **kwargs) -> dict[str, Any]:
    """Call handler, then auto-append a fresh snapshot to the result."""
    try:
        result = await handler(*args, **kwargs)
        # Find page_id from args — it's usually in a params dict or direct arg
        page_id = None
        for arg in args:
            if isinstance(arg, dict) and "page_id" in arg:
                page_id = arg["page_id"]
                break
            if isinstance(arg, str) and arg.startswith("page_"):
                page_id = arg
                break

        if page_id and not result.get("error"):
            try:
                page = _session.get_page(page_id)
                snap = await take_snapshot(page, page_id, _session, full=False, max_length=8000)
                result["_snapshot"] = snap.get("snapshot", "")
                result["_refs"] = snap.get("interactive_elements", 0)
            except Exception:
                pass

        return result
    except (PageNotFoundError, PageClosedError, BrowserSessionError) as e:
        return _err(str(e))
    except KeyError as e:
        return _err(str(e), hint="Call cloak_snapshot() first to get fresh ref IDs.")
    except Exception as e:
        err_str = str(e).lower()
        if any(kw in err_str for kw in ("closed", "crashed", "disconnected", "not connected")):
            _session._force_cleanup()
            return _err("Browser session lost. Call cloak_launch() to restart.")
        logger.exception("Tool error: %s", type(e).__name__)
        return _err(f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Tool implementations (thin wrappers calling module functions)
# ---------------------------------------------------------------------------

async def _do_launch(params: dict) -> dict:
    """Launch browser with stealth defaults."""
    if _session.is_running:
        return {"status": "already_running", "pages": _session.list_pages()}

    if _session._browser is not None or _session._context is not None:
        _session._force_cleanup()

    headless = params.get("headless", True)
    explicit_w = params.get("viewport_width")
    explicit_h = params.get("viewport_height")

    if headless:
        vp_w = explicit_w or 1920
        vp_h = explicit_h or 947
    else:
        # Headed mode: auto-detect screen size if user didn't specify
        if explicit_w and explicit_h:
            vp_w, vp_h = explicit_w, explicit_h
        else:
            from .session import detect_screen_size, compute_headed_viewport
            screen = detect_screen_size()
            auto_w, auto_h = compute_headed_viewport(screen)
            vp_w = explicit_w or auto_w
            vp_h = explicit_h or auto_h
            if screen:
                logger.info(
                    "Auto-detected screen %dx%d -> headed viewport %dx%d",
                    screen[0], screen[1], vp_w, vp_h,
                )

    cfg = SessionConfig(
        headless=headless,
        proxy=params.get("proxy"),
        humanize=params.get("humanize", True),  # Stealth default: ON
        human_preset=params.get("human_preset", "default"),
        stealth_args=params.get("stealth_args", True),
        timezone=params.get("timezone"),
        locale=params.get("locale"),
        geoip=params.get("geoip", False),
        extra_args=params.get("extra_args", []),
        fingerprint_seed=params.get("fingerprint_seed"),
        user_data_dir=params.get("user_data_dir"),
        viewport={"width": vp_w, "height": vp_h},
        color_scheme=params.get("color_scheme"),
        user_agent=params.get("user_agent"),
    )

    await _session.launch(cfg)
    page_id = await _session.new_page()

    return {
        "status": "launched",
        "page_id": page_id,
        "stealth": True,
        "humanize": cfg.humanize,
        "hint": "Next: call cloak_navigate(page_id, url) to visit a page.",
    }


async def _do_navigate(page_id: str, url: str, timeout: int) -> dict:
    """Navigate with smart waiting."""
    page = _session.get_page(page_id)
    result = await smart_navigate(page, url, timeout=timeout)
    return {
        "status": "navigated",
        "url": result["url"],
        "title": result["title"],
        "settled": result.get("settled", False),
    }


async def _do_click(page_id: str, ref: str) -> dict:
    """Click by ref with auto-retry."""
    page = _session.get_page(page_id)
    clean_ref, selector = resolve_ref(_session, page_id, ref)

    async def _click():
        await page.click(selector, timeout=5000)
        return {"status": "clicked", "ref": f"@{clean_ref}"}

    return await retry_action(_click, max_retries=1)


async def _do_type(page_id: str, ref: str, text: str, clear: bool, submit: bool) -> dict:
    """Type into element by ref."""
    page = _session.get_page(page_id)
    clean_ref, selector = resolve_ref(_session, page_id, ref)

    if clear:
        await page.fill(selector, "")
    await page.type(selector, text)
    if submit:
        await page.press(selector, "Enter")

    return {"status": "typed", "ref": f"@{clean_ref}", "length": len(text), "submitted": submit}


async def _do_select(page_id: str, ref: str, value=None, label=None, index=None) -> dict:
    """Select dropdown option by ref."""
    page = _session.get_page(page_id)
    clean_ref, selector = resolve_ref(_session, page_id, ref)

    kwargs = {}
    if value is not None:
        kwargs["value"] = value
    if label is not None:
        kwargs["label"] = label
    if index is not None:
        kwargs["index"] = index

    if not kwargs:
        return _err("Provide one of: value, label, or index.")

    selected = await page.select_option(selector, **kwargs)
    return {"status": "selected", "ref": f"@{clean_ref}", "selected": selected}


async def _do_hover(page_id: str, ref: str) -> dict:
    """Hover over element by ref."""
    page = _session.get_page(page_id)
    clean_ref, selector = resolve_ref(_session, page_id, ref)
    await page.hover(selector)
    return {"status": "hovered", "ref": f"@{clean_ref}"}


async def _do_check(page_id: str, ref: str, checked: bool) -> dict:
    """Check/uncheck checkbox by ref."""
    page = _session.get_page(page_id)
    clean_ref, selector = resolve_ref(_session, page_id, ref)

    if checked:
        await page.check(selector)
    else:
        await page.uncheck(selector)

    return {"status": "checked" if checked else "unchecked", "ref": f"@{clean_ref}"}


# ---------------------------------------------------------------------------
# Server creation
# ---------------------------------------------------------------------------

def create_server(caps: set[str] | None = None) -> FastMCP:
    """Create the CloakBrowser MCP server with registered tools."""
    global _capabilities
    _capabilities = caps or set()

    _configure_logging()

    mcp = FastMCP(
        "cloakbrowser",
        log_level=os.getenv("CLOAKBROWSER_LOG_LEVEL", "ERROR"),
        instructions=(
            "CloakBrowser — stealth browser automation with anti-detection. "
            "Source-patched Chromium that passes Cloudflare, reCAPTCHA, FingerprintJS.\n\n"
            "WORKFLOW:\n"
            "1. cloak_launch() — start stealth browser (auto-creates first page)\n"
            "2. cloak_navigate(page_id, url) — go to a URL (auto-waits for page settle)\n"
            "3. cloak_snapshot(page_id) — get interactive elements with [@eN] ref IDs\n"
            "4. cloak_click(page_id, '@e5') — click by ref from snapshot\n"
            "5. cloak_type(page_id, '@e3', 'text') — type by ref from snapshot\n"
            "6. cloak_read_page(page_id) — get page content as clean markdown\n"
            "7. cloak_close() — close browser when done\n\n"
            "IMPORTANT:\n"
            "- cloak_snapshot() is the PRIMARY way to understand pages. Call it first.\n"
            "- All interaction uses [@eN] ref IDs from snapshot. No CSS selectors.\n"
            "- cloak_read_page() returns clean markdown for reading content.\n"
            "- cloak_screenshot() returns annotated screenshots with element indices.\n"
            "- Action tools auto-return an updated snapshot."
        ),
    )

    # ===================================================================
    # CORE TOOLS (~20)
    # ===================================================================

    # --- Browser lifecycle ---

    @mcp.tool()
    async def cloak_launch(
        headless: bool = True,
        proxy: str | None = None,
        humanize: bool = True,
        human_preset: str = "default",
        stealth_args: bool = True,
        timezone: str | None = None,
        locale: str | None = None,
        geoip: bool = False,
        fingerprint_seed: str | None = None,
        user_data_dir: str | None = None,
        viewport_width: int | None = None,
        viewport_height: int | None = None,
        color_scheme: str | None = None,
        user_agent: str | None = None,
        extra_args: list[str] | None = None,
    ) -> dict[str, Any]:
        """Launch a stealth CloakBrowser instance. All anti-detection is ON by default.

        CloakBrowser is a source-patched Chromium passing Cloudflare Turnstile,
        reCAPTCHA v3 (0.9 score), FingerprintJS, BrowserScan, and 30+ detectors.

        Args:
            headless: Run headless. Some aggressive sites need headed mode (False).
            proxy: Proxy URL (e.g. 'http://user:pass@proxy:8080'). Residential recommended.
            humanize: Human-like mouse/keyboard/scroll (default: True).
            human_preset: 'default' or 'careful' (slower, more deliberate).
            stealth_args: Apply stealth fingerprint args (default: True).
            timezone: IANA timezone (e.g. 'America/New_York').
            locale: BCP 47 locale (e.g. 'en-US').
            geoip: Auto-detect timezone/locale from proxy IP.
            fingerprint_seed: Fixed seed for consistent identity across sessions.
            user_data_dir: Persistent profile path (cookies/localStorage survive restarts).
            viewport_width: Viewport width in pixels (default: 1920 headless; 1280 headed fallback, or auto-detected).
            viewport_height: Viewport height in pixels (default: 947 headless; 800 headed fallback, or auto-detected).
            color_scheme: 'light', 'dark', or 'no-preference'.
            user_agent: Custom user agent override.
            extra_args: Additional Chromium CLI flags.
        """
        return await _safe(_do_launch, {
            "headless": headless, "proxy": proxy, "humanize": humanize,
            "human_preset": human_preset, "stealth_args": stealth_args,
            "timezone": timezone, "locale": locale, "geoip": geoip,
            "fingerprint_seed": fingerprint_seed, "user_data_dir": user_data_dir,
            "viewport_width": viewport_width, "viewport_height": viewport_height,
            "color_scheme": color_scheme, "user_agent": user_agent,
            "extra_args": extra_args or [],
        })

    @mcp.tool()
    async def cloak_close() -> dict[str, Any]:
        """Close the stealth browser and release all resources. Always call when done."""
        if not _session.is_running:
            return {"status": "not_running"}
        await _session.close()
        return {"status": "closed"}

    # --- Snapshot (PRIMARY page understanding) ---

    @mcp.tool()
    async def cloak_snapshot(
        page_id: str,
        full: bool = False,
        max_length: int = 12000,
    ) -> dict[str, Any]:
        """Capture the page's accessibility tree — the PRIMARY way to understand pages.

        Returns interactive elements with [@eN] ref IDs for use with cloak_click,
        cloak_type, cloak_select, etc. Call this BEFORE interacting with a page.

        full=False (default): interactive elements only — compact and fast.
        full=True: includes surrounding text content for reading context.

        This is FASTER, CHEAPER, and MORE RELIABLE than screenshots.
        Always prefer this over cloak_screenshot for deciding what to click.

        Args:
            page_id: Target page ID from cloak_launch or cloak_new_page.
            full: Include text content alongside interactive elements.
            max_length: Max characters to return (default: 12000).
        """
        page = _session.get_page(page_id)
        return await _safe(take_snapshot, page, page_id, _session, full=full, max_length=max_length)

    # --- Ref-based interaction ---

    @mcp.tool()
    async def cloak_click(page_id: str, ref: str) -> dict[str, Any]:
        """Click an element by its [@eN] ref ID from cloak_snapshot.

        Auto-retries once if the element moved. Returns an updated snapshot.

        Args:
            page_id: Target page ID.
            ref: Ref ID from snapshot (e.g. '@e5' or 'e5').
        """
        return await _safe_snap(_do_click, page_id, ref)

    @mcp.tool()
    async def cloak_type(
        page_id: str,
        ref: str,
        text: str,
        clear: bool = True,
        submit: bool = False,
    ) -> dict[str, Any]:
        """Type text into an input by its [@eN] ref ID from cloak_snapshot.

        Clears the field first by default. Set submit=True to press Enter after.
        Returns an updated snapshot.

        Args:
            page_id: Target page ID.
            ref: Ref ID from snapshot (e.g. '@e3' or 'e3').
            text: Text to type.
            clear: Clear field before typing (default: True).
            submit: Press Enter after typing (default: False).
        """
        return await _safe_snap(_do_type, page_id, ref, text, clear, submit)

    @mcp.tool()
    async def cloak_select(
        page_id: str,
        ref: str,
        value: str | None = None,
        label: str | None = None,
        index: int | None = None,
    ) -> dict[str, Any]:
        """Select a dropdown option by ref ID. Provide one of: value, label, or index.

        Returns an updated snapshot.

        Args:
            page_id: Target page ID.
            ref: Ref ID of the <select> element.
            value: Option value attribute to select.
            label: Option visible text to select.
            index: Option index (0-based) to select.
        """
        return await _safe_snap(_do_select, page_id, ref, value, label, index)

    @mcp.tool()
    async def cloak_hover(page_id: str, ref: str) -> dict[str, Any]:
        """Hover over an element by ref ID. Returns an updated snapshot.

        Args:
            page_id: Target page ID.
            ref: Ref ID from snapshot.
        """
        return await _safe_snap(_do_hover, page_id, ref)

    @mcp.tool()
    async def cloak_check(page_id: str, ref: str, checked: bool = True) -> dict[str, Any]:
        """Check or uncheck a checkbox/radio by ref ID. Returns an updated snapshot.

        Args:
            page_id: Target page ID.
            ref: Ref ID from snapshot.
            checked: True to check, False to uncheck.
        """
        return await _safe_snap(_do_check, page_id, ref, checked)

    # --- Content extraction ---

    @mcp.tool()
    async def cloak_read_page(
        page_id: str,
        max_length: int = 50000,
    ) -> dict[str, Any]:
        """Get the page content as clean, readable markdown.

        Best for reading articles, docs, search results, or any content-heavy page.
        Strips navigation, ads, footers — returns just the main content.
        Much more token-efficient than raw HTML (60-80% savings).

        Args:
            page_id: Target page ID.
            max_length: Max characters to return (default: 50000).
        """
        page = _session.get_page(page_id)
        return await _safe(extract_markdown, page, max_length=max_length)

    @mcp.tool()
    async def cloak_screenshot(
        page_id: str,
        full_page: bool = False,
    ) -> dict[str, Any]:
        """Take an annotated screenshot with element indices overlaid.

        Each numbered element maps to [@eN] refs from cloak_snapshot.
        Use when you need VISUAL context — images, charts, CAPTCHAs, or layout.
        For most interactions, prefer cloak_snapshot() instead.

        Returns: file path to saved PNG, element count.

        Args:
            page_id: Target page ID.
            full_page: Capture entire scrollable page (default: viewport only).
        """
        page = _session.get_page(page_id)
        return await _safe(take_annotated_screenshot, page, page_id, _session, full_page=full_page)

    # --- Navigation ---

    @mcp.tool()
    async def cloak_navigate(
        page_id: str,
        url: str,
        timeout: int = 30000,
    ) -> dict[str, Any]:
        """Navigate to a URL. Auto-waits for the page to settle (network idle + DOM stable).

        Handles Cloudflare challenge pages with extra wait time.
        Returns an updated snapshot of the loaded page.

        Args:
            page_id: Target page ID.
            url: URL to navigate to.
            timeout: Navigation timeout in milliseconds.
        """
        return await _safe_snap(_do_navigate, page_id, url, timeout)

    @mcp.tool()
    async def cloak_back(page_id: str) -> dict[str, Any]:
        """Navigate back in browser history. Returns an updated snapshot.

        Args:
            page_id: Target page ID.
        """
        async def _go_back(pid):
            page = _session.get_page(pid)
            await page.go_back()
            await wait_for_settle(page)
            title = await page.title()
            return {"url": page.url, "title": title}

        return await _safe_snap(_go_back, page_id)

    @mcp.tool()
    async def cloak_forward(page_id: str) -> dict[str, Any]:
        """Navigate forward in browser history. Returns an updated snapshot.

        Args:
            page_id: Target page ID.
        """
        async def _go_fwd(pid):
            page = _session.get_page(pid)
            await page.go_forward()
            await wait_for_settle(page)
            title = await page.title()
            return {"url": page.url, "title": title}

        return await _safe_snap(_go_fwd, page_id)

    # --- Keyboard & scroll ---

    @mcp.tool()
    async def cloak_press_key(
        page_id: str,
        key: str,
    ) -> dict[str, Any]:
        """Press a keyboard key (Enter, Tab, Escape, ArrowDown, etc.).

        Returns an updated snapshot.

        Args:
            page_id: Target page ID.
            key: Key name (DOM KeyboardEvent key).
        """
        async def _press(pid, k):
            page = _session.get_page(pid)
            await page.keyboard.press(k)
            return {"status": "pressed", "key": k}

        return await _safe_snap(_press, page_id, key)

    @mcp.tool()
    async def cloak_scroll(
        page_id: str,
        direction: str = "down",
        amount: int = 500,
    ) -> dict[str, Any]:
        """Scroll the page. Returns an updated snapshot.

        Args:
            page_id: Target page ID.
            direction: 'up' or 'down'.
            amount: Pixels to scroll.
        """
        async def _scroll(pid, d, a):
            page = _session.get_page(pid)
            delta = a if d == "down" else -a
            await page.evaluate(f"window.scrollBy(0, {delta})")
            return {"status": "scrolled", "direction": d, "amount": a}

        return await _safe_snap(_scroll, page_id, direction, amount)

    # --- Wait ---

    @mcp.tool()
    async def cloak_wait(
        page_id: str,
        timeout_ms: int = 5000,
    ) -> dict[str, Any]:
        """Wait for the page to settle (no DOM mutations + network idle).

        Use after actions that trigger dynamic content loading.
        Returns whether the page settled and how many DOM mutations occurred.

        Args:
            page_id: Target page ID.
            timeout_ms: Max wait time in milliseconds (default: 5000).
        """
        page = _session.get_page(page_id)
        return await _safe(wait_for_settle, page, timeout_ms=timeout_ms)

    # --- JavaScript ---

    @mcp.tool()
    async def cloak_evaluate(page_id: str, expression: str) -> dict[str, Any]:
        """Execute JavaScript in the page context and return the result.

        Args:
            page_id: Target page ID.
            expression: JavaScript expression to evaluate.
        """
        async def _eval(pid, expr):
            page = _session.get_page(pid)
            result = await page.evaluate(expr)
            # Ensure JSON-serializable
            try:
                json.dumps(result)
            except (TypeError, ValueError):
                result = str(result)
            if isinstance(result, str) and len(result) > 500_000:
                result = result[:500_000] + "\n[... truncated]"
            return {"result": result}

        return await _safe(_eval, page_id, expression)

    # --- Page management ---

    @mcp.tool()
    async def cloak_new_page(url: str | None = None) -> dict[str, Any]:
        """Open a new browser page/tab. Optionally navigate to a URL.

        Args:
            url: URL to navigate to after creating the page.
        """
        async def _new(u):
            pid = await _session.new_page()
            page = _session.get_page(pid)
            if u:
                await smart_navigate(page, u)
            return {"page_id": pid, "url": page.url}

        return await _safe(_new, url)

    @mcp.tool()
    async def cloak_list_pages() -> dict[str, Any]:
        """List all open pages with their IDs and URLs."""
        return {"pages": _session.list_pages()}

    @mcp.tool()
    async def cloak_close_page(page_id: str) -> dict[str, Any]:
        """Close a specific page by ID.

        Args:
            page_id: Page ID to close.
        """
        async def _close(pid):
            await _session.close_page(pid)
            return {"status": "closed", "page_id": pid}

        return await _safe(_close, page_id)

    # ===================================================================
    # CAPABILITY-GATED TOOLS (enabled via --caps flag)
    # ===================================================================

    if "network" in _capabilities or "all" in _capabilities:

        @mcp.tool()
        async def cloak_network_intercept(
            page_id: str,
            url_pattern: str,
            action: str = "block",
            mock_body: str = "",
            mock_status: int = 200,
            mock_content_type: str = "application/json",
        ) -> dict[str, Any]:
            """Intercept network requests — block, mock, or passthrough.

            Args:
                page_id: Target page ID.
                url_pattern: Glob pattern (e.g. '**/api/**', '**/*.png').
                action: 'block', 'mock', or 'continue'.
                mock_body: Response body for 'mock' action.
                mock_status: HTTP status for 'mock' action.
                mock_content_type: Content-Type for 'mock' action.
            """
            page = _session.get_page(page_id)
            return await _safe(
                setup_intercept, page, page_id, url_pattern,
                action=action, mock_body=mock_body,
                mock_status=mock_status, mock_content_type=mock_content_type,
            )

        @mcp.tool()
        async def cloak_network_continue(page_id: str, url_pattern: str) -> dict[str, Any]:
            """Remove a network interception rule.

            Args:
                page_id: Target page ID.
                url_pattern: Same pattern used in cloak_network_intercept.
            """
            page = _session.get_page(page_id)
            return await _safe(remove_intercept, page, page_id, url_pattern)

    if "cookies" in _capabilities or "all" in _capabilities:

        @mcp.tool()
        async def cloak_get_cookies(page_id: str) -> dict[str, Any]:
            """Get all cookies from the page's browser context.

            Args:
                page_id: Target page ID.
            """
            page = _session.get_page(page_id)
            return await _safe(_get_cookies, page)

        @mcp.tool()
        async def cloak_set_cookies(page_id: str, cookies: list[dict]) -> dict[str, Any]:
            """Set cookies in the page's browser context.

            Args:
                page_id: Target page ID.
                cookies: List of cookie dicts with name, value, domain, path.
            """
            page = _session.get_page(page_id)
            return await _safe(_set_cookies, page, cookies)

    if "pdf" in _capabilities or "all" in _capabilities:

        @mcp.tool()
        async def cloak_pdf(
            page_id: str,
            format: str = "A4",
            print_background: bool = True,
        ) -> dict[str, Any]:
            """Save the current page as a PDF file.

            Args:
                page_id: Target page ID.
                format: Page format — 'A4', 'Letter', 'Legal'.
                print_background: Include background graphics.
            """
            from pathlib import Path
            import time

            async def _pdf(pid, fmt, bg):
                page = _session.get_page(pid)
                ts = int(time.time() * 1000)
                fp = Path.home() / ".cloakbrowser" / "artifacts" / f"page_{ts}.pdf"
                fp.parent.mkdir(parents=True, exist_ok=True)
                pdf_bytes = await page.pdf(format=fmt, print_background=bg)
                fp.write_bytes(pdf_bytes)
                return {"path": str(fp), "size_bytes": len(pdf_bytes)}

            return await _safe(_pdf, page_id, format, print_background)

    if "console" in _capabilities or "all" in _capabilities:

        @mcp.tool()
        async def cloak_console(page_id: str, clear: bool = False) -> dict[str, Any]:
            """Get browser console output (log/warn/error/info) and JS errors.

            Args:
                page_id: Target page ID.
                clear: Clear the message buffer after reading.
            """
            messages = _session.get_console_messages(page_id)[-100:]
            if clear:
                _session.clear_console_messages(page_id)
            return {"messages": messages, "count": len(messages)}

    # ===================================================================
    # MCP Prompts
    # ===================================================================

    @mcp.prompt()
    def browse_and_extract(url: str, what: str = "main content") -> str:
        """Browse a URL and extract content.

        Args:
            url: URL to visit.
            what: What to extract.
        """
        return (
            f"Use CloakBrowser to visit {url} and extract: {what}\n\n"
            "1. cloak_launch()\n"
            "2. cloak_navigate(page_id, url)\n"
            "3. cloak_snapshot(page_id) to see structure\n"
            "4. cloak_read_page(page_id) to get markdown content\n"
            "5. Extract the requested information\n"
            "6. cloak_close()\n"
        )

    @mcp.prompt()
    def fill_form(url: str, instructions: str = "") -> str:
        """Fill and submit a form.

        Args:
            url: URL with the form.
            instructions: What to fill in.
        """
        return (
            f"Use CloakBrowser to fill a form at {url}\n"
            f"Instructions: {instructions}\n\n"
            "1. cloak_launch()\n"
            "2. cloak_navigate(page_id, url)\n"
            "3. cloak_snapshot(page_id) to see form fields with ref IDs\n"
            "4. cloak_type(page_id, ref, value) for each field\n"
            "5. cloak_screenshot(page_id) to verify before submit\n"
            "6. cloak_click(page_id, submit_ref) to submit\n"
            "7. cloak_read_page(page_id) to see result\n"
            "8. cloak_close()\n"
        )

    @mcp.prompt()
    def login(url: str, username: str = "", password: str = "") -> str:
        """Log into a website.

        Args:
            url: Login page URL.
            username: Username/email.
            password: Password.
        """
        return (
            f"Use CloakBrowser to log into {url}\n\n"
            "1. cloak_launch()  # stealth + humanize ON by default\n"
            "2. cloak_navigate(page_id, url)\n"
            "3. cloak_snapshot(page_id) to find username/password fields\n"
            f"4. cloak_type(page_id, username_ref, '{username or '[ask]'}')\n"
            f"5. cloak_type(page_id, password_ref, '{password or '[ask]'}')\n"
            "6. cloak_click(page_id, sign_in_ref)\n"
            "7. cloak_snapshot(page_id) to verify login succeeded\n"
        )

    return mcp


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """Entry point for the cloakbrowsermcp CLI."""
    import argparse

    parser = argparse.ArgumentParser(description="CloakBrowser MCP Server")
    parser.add_argument(
        "--caps",
        type=str,
        default="",
        help="Comma-separated capabilities to enable: network, cookies, pdf, console, all",
    )
    parser.add_argument(
        "--transport",
        type=str,
        default="stdio",
        choices=["stdio", "sse", "streamable-http"],
        help="MCP transport (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8931,
        help="Port for SSE transport (default: 8931)",
    )

    args = parser.parse_args()

    caps = set()
    if args.caps:
        caps = {c.strip().lower() for c in args.caps.split(",")}

    _configure_logging()
    server = create_server(caps=caps)

    if args.transport == "sse":
        server.run(transport="sse", port=args.port)
    elif args.transport == "streamable-http":
        server.run(transport="streamable-http", port=args.port)
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
