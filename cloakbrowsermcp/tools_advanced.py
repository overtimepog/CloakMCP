"""Advanced MCP tool handlers — stealth config, network interception, navigation helpers.

These tools provide deeper CloakBrowser integration beyond basic Playwright operations.
"""

from __future__ import annotations

import logging
from typing import Any

from cloakbrowser import binary_info
from cloakbrowser.config import get_default_stealth_args

from .session import BrowserSession

logger = logging.getLogger("cloakbrowsermcp")


# ---------------------------------------------------------------------------
# Stealth inspection
# ---------------------------------------------------------------------------

async def handle_stealth_config(params: dict) -> dict:
    """Return the current default stealth configuration."""
    args = get_default_stealth_args()
    return {
        "args": args,
        "description": "Default CloakBrowser stealth args applied to every launch.",
    }


async def handle_get_binary_info(params: dict) -> dict:
    """Return info about the CloakBrowser binary."""
    info = binary_info()
    return dict(info)


# ---------------------------------------------------------------------------
# Network interception
# ---------------------------------------------------------------------------

# Store route handlers per page so they can be removed
_route_handlers: dict[str, dict[str, Any]] = {}


async def handle_network_intercept(session: BrowserSession, params: dict) -> dict:
    """Set up network request interception on a page."""
    page = session.get_page(params["page_id"])
    url_pattern = params["url_pattern"]
    action = params.get("action", "block")

    async def route_handler(route):
        if action == "block":
            await route.abort()
        elif action == "mock":
            body = params.get("mock_body", "")
            status = params.get("mock_status", 200)
            content_type = params.get("mock_content_type", "application/json")
            await route.fulfill(status=status, body=body, content_type=content_type)
        else:
            await route.continue_()

    await page.route(url_pattern, route_handler)

    # Track handler for removal
    page_id = params["page_id"]
    if page_id not in _route_handlers:
        _route_handlers[page_id] = {}
    _route_handlers[page_id][url_pattern] = route_handler

    return {"status": "intercepting", "url_pattern": url_pattern, "action": action}


async def handle_network_continue(session: BrowserSession, params: dict) -> dict:
    """Remove a network interception route."""
    page = session.get_page(params["page_id"])
    url_pattern = params["url_pattern"]
    page_id = params["page_id"]

    handler = _route_handlers.get(page_id, {}).get(url_pattern)
    if handler:
        await page.unroute(url_pattern, handler)
        del _route_handlers[page_id][url_pattern]
    else:
        await page.unroute(url_pattern)

    return {"status": "unrouted", "url_pattern": url_pattern}


# ---------------------------------------------------------------------------
# Navigation helpers
# ---------------------------------------------------------------------------

async def handle_wait_for_navigation(session: BrowserSession, params: dict) -> dict:
    """Wait for the page to reach a specific load state."""
    page = session.get_page(params["page_id"])
    state = params.get("state", "domcontentloaded")
    timeout = params.get("timeout", 30000)

    await page.wait_for_load_state(state, timeout=timeout)

    title = await page.title()
    return {"status": "loaded", "url": page.url, "title": title}


async def handle_go_back(session: BrowserSession, params: dict) -> dict:
    """Navigate back in page history."""
    page = session.get_page(params["page_id"])
    await page.go_back()

    title = await page.title()
    return {"url": page.url, "title": title}


async def handle_go_forward(session: BrowserSession, params: dict) -> dict:
    """Navigate forward in page history."""
    page = session.get_page(params["page_id"])
    await page.go_forward()

    title = await page.title()
    return {"url": page.url, "title": title}


async def handle_reload(session: BrowserSession, params: dict) -> dict:
    """Reload the current page."""
    page = session.get_page(params["page_id"])
    await page.reload()

    title = await page.title()
    return {"status": "reloaded", "url": page.url, "title": title}


# ---------------------------------------------------------------------------
# Viewport & media
# ---------------------------------------------------------------------------

async def handle_set_viewport(session: BrowserSession, params: dict) -> dict:
    """Set the viewport size of a page."""
    page = session.get_page(params["page_id"])
    width = params["width"]
    height = params["height"]

    await page.set_viewport_size({"width": width, "height": height})

    return {"status": "viewport_set", "width": width, "height": height}


async def handle_emulate_media(session: BrowserSession, params: dict) -> dict:
    """Emulate media features (color scheme, media type, etc.)."""
    page = session.get_page(params["page_id"])

    emulate_kwargs = {}
    if "color_scheme" in params:
        emulate_kwargs["color_scheme"] = params["color_scheme"]
    if "media" in params:
        emulate_kwargs["media"] = params["media"]
    if "reduced_motion" in params:
        emulate_kwargs["reduced_motion"] = params["reduced_motion"]

    await page.emulate_media(**emulate_kwargs)

    return {"status": "emulated", **emulate_kwargs}


# ---------------------------------------------------------------------------
# Page scripting
# ---------------------------------------------------------------------------

async def handle_add_init_script(session: BrowserSession, params: dict) -> dict:
    """Add an initialization script that runs before page scripts."""
    page = session.get_page(params["page_id"])
    script = params["script"]

    await page.add_init_script(script)

    return {"status": "added", "script_length": len(script)}
