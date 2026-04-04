"""Network interception and cookie management for CloakBrowser MCP v2."""

from typing import Any

# Storage: {page_id: {url_pattern: handler_fn}}
_route_handlers: dict[str, dict[str, Any]] = {}


async def setup_intercept(
    page,
    page_id: str,
    url_pattern: str,
    action: str = "block",
    mock_body: str = "",
    mock_status: int = 200,
    mock_content_type: str = "application/json",
) -> dict:
    """Set up a route intercept on the page."""

    async def handler(route):
        if action == "block":
            await route.abort()
        elif action == "mock":
            await route.fulfill(
                status=mock_status,
                content_type=mock_content_type,
                body=mock_body,
            )
        else:
            await route.continue_()

    # Remove existing handler for this pattern if any
    await remove_intercept(page, page_id, url_pattern)

    # Register new handler
    await page.route(url_pattern, handler)

    if page_id not in _route_handlers:
        _route_handlers[page_id] = {}
    _route_handlers[page_id][url_pattern] = handler

    return {
        "page_id": page_id,
        "url_pattern": url_pattern,
        "action": action,
        "active": True,
    }


async def remove_intercept(page, page_id: str, url_pattern: str) -> dict:
    """Remove a route intercept from the page."""
    removed = False

    if page_id in _route_handlers and url_pattern in _route_handlers[page_id]:
        handler = _route_handlers[page_id].pop(url_pattern)
        try:
            await page.unroute(url_pattern, handler)
        except Exception:
            pass
        removed = True
        if not _route_handlers[page_id]:
            del _route_handlers[page_id]

    return {"page_id": page_id, "url_pattern": url_pattern, "removed": removed}


async def get_cookies(page) -> dict:
    """Get all cookies from the page's browser context."""
    context = page.context
    cookies = await context.cookies()
    return {"cookies": cookies, "count": len(cookies)}


async def set_cookies(page, cookies: list[dict]) -> dict:
    """Set cookies on the page's browser context."""
    context = page.context
    await context.add_cookies(cookies)
    return {"set": len(cookies), "success": True}
