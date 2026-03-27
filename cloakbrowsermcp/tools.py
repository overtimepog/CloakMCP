"""Core MCP tool handlers — browser automation operations.

Each handler takes a BrowserSession and a params dict, returning a result dict.
This keeps tool logic independent from MCP registration.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from .session import BrowserSession, SessionConfig

logger = logging.getLogger("cloakbrowsermcp")


# ---------------------------------------------------------------------------
# Browser lifecycle
# ---------------------------------------------------------------------------

async def handle_launch_browser(session: BrowserSession, params: dict) -> dict:
    """Launch a stealth CloakBrowser instance."""
    if session.is_running:
        return {"status": "Already running. Close first or use existing session.", "pages": session.list_pages()}

    cfg = SessionConfig(
        headless=params.get("headless", True),
        proxy=params.get("proxy"),
        humanize=params.get("humanize", False),
        human_preset=params.get("human_preset", "default"),
        human_config=params.get("human_config"),
        stealth_args=params.get("stealth_args", True),
        timezone=params.get("timezone"),
        locale=params.get("locale"),
        geoip=params.get("geoip", False),
        extra_args=params.get("extra_args", []),
        fingerprint_seed=params.get("fingerprint_seed"),
        user_data_dir=params.get("user_data_dir"),
        viewport=params.get("viewport", {"width": 1920, "height": 947}),
        color_scheme=params.get("color_scheme"),
        user_agent=params.get("user_agent"),
        backend=params.get("backend"),
    )

    await session.launch(cfg)

    # Auto-create first page
    page_id = await session.new_page()

    return {
        "status": "launched",
        "page_id": page_id,
        "headless": cfg.headless,
        "humanize": cfg.humanize,
        "persistent": cfg.user_data_dir is not None,
    }


async def handle_close_browser(session: BrowserSession, params: dict) -> dict:
    """Close the browser and all pages."""
    if not session.is_running:
        return {"status": "Not running"}

    await session.close()
    return {"status": "closed"}


# ---------------------------------------------------------------------------
# Page lifecycle
# ---------------------------------------------------------------------------

async def handle_new_page(session: BrowserSession, params: dict) -> dict:
    """Open a new browser page/tab."""
    page_id = await session.new_page()
    page = session.get_page(page_id)

    url = params.get("url")
    if url:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

    return {
        "page_id": page_id,
        "url": page.url,
    }


async def handle_close_page(session: BrowserSession, params: dict) -> dict:
    """Close a specific page."""
    page_id = params["page_id"]
    await session.close_page(page_id)
    return {"status": "closed", "page_id": page_id}


async def handle_list_pages(session: BrowserSession, params: dict) -> dict:
    """List all open pages."""
    return {"pages": session.list_pages()}


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

async def handle_navigate(session: BrowserSession, params: dict) -> dict:
    """Navigate a page to a URL."""
    page = session.get_page(params["page_id"])
    url = params["url"]
    wait_until = params.get("wait_until", "domcontentloaded")
    timeout = params.get("timeout", 30000)

    await page.goto(url, wait_until=wait_until, timeout=timeout)

    title = await page.title()
    return {
        "url": page.url,
        "title": title,
    }


# ---------------------------------------------------------------------------
# Interaction
# ---------------------------------------------------------------------------

async def handle_click(session: BrowserSession, params: dict) -> dict:
    """Click an element on the page."""
    page = session.get_page(params["page_id"])
    selector = params["selector"]
    timeout = params.get("timeout", 5000)

    await page.click(selector, timeout=timeout)

    return {"status": "clicked", "selector": selector}


async def handle_type_text(session: BrowserSession, params: dict) -> dict:
    """Type text into an element. Uses page.type() for realistic keystroke events."""
    page = session.get_page(params["page_id"])
    selector = params["selector"]
    text = params["text"]
    delay = params.get("delay", 0)

    await page.type(selector, text, delay=delay)

    return {"status": "typed", "selector": selector, "length": len(text)}


async def handle_fill_form(session: BrowserSession, params: dict) -> dict:
    """Fill a form field using page.fill() — sets value directly."""
    page = session.get_page(params["page_id"])
    selector = params["selector"]
    value = params["value"]

    await page.fill(selector, value)

    return {"status": "filled", "selector": selector}


async def handle_hover(session: BrowserSession, params: dict) -> dict:
    """Hover over an element."""
    page = session.get_page(params["page_id"])
    selector = params["selector"]

    await page.hover(selector)

    return {"status": "hovered", "selector": selector}


async def handle_select_option(session: BrowserSession, params: dict) -> dict:
    """Select an option from a <select> element."""
    page = session.get_page(params["page_id"])
    selector = params["selector"]

    kwargs = {}
    if "value" in params:
        kwargs["value"] = params["value"]
    if "label" in params:
        kwargs["label"] = params["label"]
    if "index" in params:
        kwargs["index"] = params["index"]

    selected = await page.select_option(selector, **kwargs)

    return {"selected": selected, "selector": selector}


async def handle_press_key(session: BrowserSession, params: dict) -> dict:
    """Press a keyboard key."""
    page = session.get_page(params["page_id"])
    key = params["key"]

    selector = params.get("selector")
    if selector:
        await page.press(selector, key)
    else:
        await page.keyboard.press(key)

    return {"status": "pressed", "key": key}


async def handle_scroll(session: BrowserSession, params: dict) -> dict:
    """Scroll the page in a direction."""
    page = session.get_page(params["page_id"])
    direction = params.get("direction", "down")
    amount = params.get("amount", 300)

    delta_y = amount if direction == "down" else -amount
    await page.evaluate(f"window.scrollBy(0, {delta_y})")

    return {"status": "scrolled", "direction": direction, "amount": amount}


# ---------------------------------------------------------------------------
# Content extraction
# ---------------------------------------------------------------------------

async def handle_screenshot(session: BrowserSession, params: dict) -> dict:
    """Take a screenshot of the page or a specific element."""
    page = session.get_page(params["page_id"])

    selector = params.get("selector")
    full_page = params.get("full_page", False)

    if selector:
        locator = page.locator(selector)
        screenshot_bytes = await locator.screenshot()
    else:
        screenshot_bytes = await page.screenshot(full_page=full_page)

    b64_data = base64.b64encode(screenshot_bytes).decode("utf-8")

    return {
        "data": b64_data,
        "mime_type": "image/png",
        "size_bytes": len(screenshot_bytes),
    }


async def handle_get_content(session: BrowserSession, params: dict) -> dict:
    """Get page content — HTML, text, or outer HTML of a selector."""
    page = session.get_page(params["page_id"])
    selector = params.get("selector")
    content_type = params.get("content_type", "html")

    if content_type == "text" and selector:
        content = await page.inner_text(selector)
    elif content_type == "outer_html" and selector:
        locator = page.locator(selector)
        content = await locator.evaluate("el => el.outerHTML")
    elif selector:
        content = await page.inner_html(selector)
    else:
        content = await page.content()

    return {"content": content, "content_type": content_type}


async def handle_evaluate(session: BrowserSession, params: dict) -> dict:
    """Execute JavaScript in the page context."""
    page = session.get_page(params["page_id"])
    expression = params["expression"]

    result = await page.evaluate(expression)

    return {"result": result}


async def handle_wait_for_selector(session: BrowserSession, params: dict) -> dict:
    """Wait for a selector to appear or disappear."""
    page = session.get_page(params["page_id"])
    selector = params["selector"]
    state = params.get("state", "visible")
    timeout = params.get("timeout", 30000)

    await page.wait_for_selector(selector, state=state, timeout=timeout)

    return {"status": "found", "selector": selector, "state": state}


# ---------------------------------------------------------------------------
# Cookies
# ---------------------------------------------------------------------------

async def handle_get_cookies(session: BrowserSession, params: dict) -> dict:
    """Get cookies from the page's browser context."""
    page = session.get_page(params["page_id"])
    cookies = await page.context.cookies()
    return {"cookies": cookies}


async def handle_set_cookies(session: BrowserSession, params: dict) -> dict:
    """Set cookies in the page's browser context."""
    page = session.get_page(params["page_id"])
    cookies = params["cookies"]
    await page.context.add_cookies(cookies)
    return {"status": "set", "count": len(cookies)}


# ---------------------------------------------------------------------------
# Page info & export
# ---------------------------------------------------------------------------

async def handle_get_page_info(session: BrowserSession, params: dict) -> dict:
    """Get current page URL and title."""
    page = session.get_page(params["page_id"])
    title = await page.title()
    return {
        "url": page.url,
        "title": title,
    }


async def handle_pdf(session: BrowserSession, params: dict) -> dict:
    """Generate a PDF of the current page."""
    page = session.get_page(params["page_id"])

    pdf_kwargs = {}
    if "format" in params:
        pdf_kwargs["format"] = params["format"]
    if "print_background" in params:
        pdf_kwargs["print_background"] = params["print_background"]

    pdf_bytes = await page.pdf(**pdf_kwargs)
    b64_data = base64.b64encode(pdf_bytes).decode("utf-8")

    return {
        "data": b64_data,
        "mime_type": "application/pdf",
        "size_bytes": len(pdf_bytes),
    }
