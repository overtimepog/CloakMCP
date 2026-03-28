"""Core MCP tool handlers — browser automation operations.

Each handler takes a BrowserSession and a params dict, returning a result dict.
This keeps tool logic independent from MCP registration.
"""

from __future__ import annotations

import base64
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from .session import BrowserSession, SessionConfig, BrowserSessionError, PageNotFoundError, PageClosedError

logger = logging.getLogger("cloakbrowsermcp")

# Directory for saving screenshots and PDFs
ARTIFACTS_DIR = Path.home() / ".cloakbrowser" / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Snapshot — accessibility tree with ref IDs (the killer agent feature)
# ---------------------------------------------------------------------------

# JavaScript to build an accessibility-tree-like snapshot with ref IDs
_SNAPSHOT_JS = """
(() => {
    const INTERACTIVE = new Set([
        'A', 'BUTTON', 'INPUT', 'TEXTAREA', 'SELECT', 'DETAILS', 'SUMMARY'
    ]);
    const INTERACTIVE_ROLES = new Set([
        'button', 'link', 'textbox', 'checkbox', 'radio', 'combobox',
        'menuitem', 'tab', 'switch', 'slider', 'spinbutton', 'searchbox',
        'option', 'menuitemcheckbox', 'menuitemradio', 'treeitem'
    ]);

    let refCounter = 0;
    const refs = {};
    const lines = [];

    function isVisible(el) {
        if (!el.offsetParent && el.tagName !== 'BODY' && el.tagName !== 'HTML'
            && getComputedStyle(el).position !== 'fixed'
            && getComputedStyle(el).position !== 'sticky') return false;
        const style = getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        return true;
    }

    function isInteractive(el) {
        if (INTERACTIVE.has(el.tagName)) return true;
        const role = el.getAttribute('role');
        if (role && INTERACTIVE_ROLES.has(role)) return true;
        if (el.hasAttribute('tabindex') && el.tabIndex >= 0) return true;
        if (el.hasAttribute('onclick') || el.hasAttribute('contenteditable')) return true;
        return false;
    }

    function getLabel(el) {
        // aria-label first
        const ariaLabel = el.getAttribute('aria-label');
        if (ariaLabel) return ariaLabel;

        // Associated label element
        if (el.id) {
            const label = document.querySelector('label[for="' + el.id + '"]');
            if (label) return label.innerText.trim();
        }

        // Placeholder
        if (el.placeholder) return el.placeholder;

        // Title
        if (el.title) return el.title;

        // Inner text (short)
        const text = el.innerText || el.textContent || '';
        return text.trim().substring(0, 120);
    }

    function getSelector(el) {
        if (el.id) return '#' + CSS.escape(el.id);
        if (el.name && el.tagName !== 'A') {
            return el.tagName.toLowerCase() + '[name="' + el.name + '"]';
        }
        // Build a path
        const path = [];
        let current = el;
        while (current && current !== document.body) {
            let seg = current.tagName.toLowerCase();
            if (current.id) {
                seg = '#' + CSS.escape(current.id);
                path.unshift(seg);
                break;
            }
            const parent = current.parentElement;
            if (parent) {
                const siblings = Array.from(parent.children).filter(c => c.tagName === current.tagName);
                if (siblings.length > 1) {
                    const idx = siblings.indexOf(current) + 1;
                    seg += ':nth-of-type(' + idx + ')';
                }
            }
            path.unshift(seg);
            current = current.parentElement;
        }
        return path.join(' > ');
    }

    function describeElement(el) {
        const tag = el.tagName.toLowerCase();
        const role = el.getAttribute('role') || '';
        const type = el.getAttribute('type') || '';
        const label = getLabel(el);
        const value = el.value || '';
        const checked = el.checked;
        const disabled = el.disabled;
        const href = el.href || '';

        let desc = '';

        if (tag === 'a') {
            desc = 'link';
            if (label) desc += ' "' + label + '"';
            if (href) desc += ' -> ' + href;
        } else if (tag === 'button' || role === 'button') {
            desc = 'button';
            if (label) desc += ' "' + label + '"';
        } else if (tag === 'input') {
            desc = type || 'text';
            desc += ' input';
            if (label) desc += ' "' + label + '"';
            if (value) desc += ' value="' + value.substring(0, 80) + '"';
            if (type === 'checkbox' || type === 'radio') {
                desc += checked ? ' [checked]' : ' [unchecked]';
            }
        } else if (tag === 'textarea') {
            desc = 'textarea';
            if (label) desc += ' "' + label + '"';
            if (value) desc += ' value="' + value.substring(0, 80) + '"';
        } else if (tag === 'select') {
            desc = 'select';
            if (label) desc += ' "' + label + '"';
            const selected = el.options[el.selectedIndex];
            if (selected) desc += ' selected="' + selected.text + '"';
        } else if (tag === 'details') {
            desc = el.open ? 'details [open]' : 'details [closed]';
            if (label) desc += ' "' + label + '"';
        } else if (tag === 'summary') {
            desc = 'summary';
            if (label) desc += ' "' + label + '"';
        } else {
            desc = role || tag;
            if (label) desc += ' "' + label + '"';
        }

        if (disabled) desc += ' [disabled]';
        return desc;
    }

    function walk(el, depth, fullMode) {
        if (!el || !isVisible(el)) return;

        const tag = el.tagName;
        if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT' || tag === 'SVG') return;

        const interactive = isInteractive(el);

        if (interactive) {
            const ref = 'e' + (++refCounter);
            const selector = getSelector(el);
            const desc = describeElement(el);
            refs[ref] = { selector: selector, tag: tag.toLowerCase() };
            const indent = '  '.repeat(depth);
            lines.push(indent + '[@' + ref + '] ' + desc);
        } else if (fullMode) {
            // In full mode, show structural text nodes too
            const text = el.innerText || '';
            if (text.trim() && el.children.length === 0) {
                const indent = '  '.repeat(depth);
                const truncated = text.trim().substring(0, 200);
                if (truncated) lines.push(indent + truncated);
            }
        }

        for (const child of el.children) {
            walk(child, interactive ? depth + 1 : depth, fullMode);
        }
    }

    // Add page info header
    lines.push('Page: ' + document.title);
    lines.push('URL: ' + location.href);
    lines.push('---');

    const fullMode = !!window.__snapshot_full_mode;
    walk(document.body, 0, fullMode);

    // Store ref map globally so click_ref can use it
    window.__cloakbrowser_refs = refs;

    return {
        snapshot: lines.join('\\n'),
        ref_count: refCounter,
        refs: refs
    };
})()
"""

_SNAPSHOT_FULL_MODE_ENABLE = "window.__snapshot_full_mode = true;"
_SNAPSHOT_FULL_MODE_DISABLE = "window.__snapshot_full_mode = false;"


async def handle_snapshot(session: BrowserSession, params: dict) -> dict:
    """Get a text-based snapshot of the page's interactive elements with ref IDs.

    Returns an accessibility-tree-like view where each interactive element
    gets a [@eN] ref ID that can be used with click_ref, type_ref, etc.
    """
    page = session.get_page(params["page_id"])
    full = params.get("full", False)

    if full:
        await page.evaluate(_SNAPSHOT_FULL_MODE_ENABLE)
    else:
        await page.evaluate(_SNAPSHOT_FULL_MODE_DISABLE)

    result = await page.evaluate(_SNAPSHOT_JS)
    snapshot_text = result["snapshot"]
    ref_count = result["ref_count"]

    # Store refs in session for click_ref/type_ref
    session.set_refs(params["page_id"], result["refs"])

    # Truncate if too long
    max_length = params.get("max_length", 8000)
    truncated = False
    if len(snapshot_text) > max_length:
        snapshot_text = snapshot_text[:max_length] + "\n\n[... truncated, use selector-specific snapshot]"
        truncated = True

    return {
        "snapshot": snapshot_text,
        "interactive_elements": ref_count,
        "truncated": truncated,
    }


async def handle_click_ref(session: BrowserSession, params: dict) -> dict:
    """Click an element by its ref ID from a snapshot."""
    page = session.get_page(params["page_id"])
    ref = params["ref"].lstrip("@")  # Accept both 'e5' and '@e5'

    refs = session.get_refs(params["page_id"])
    if ref not in refs:
        return {"error": f"Ref @{ref} not found. Take a new snapshot first."}

    selector = refs[ref]["selector"]
    try:
        await page.click(selector, timeout=5000)
        return {"status": "clicked", "ref": f"@{ref}", "selector": selector}
    except Exception as e:
        return {"error": f"Failed to click @{ref} ({selector}): {e}"}


async def handle_type_ref(session: BrowserSession, params: dict) -> dict:
    """Type text into an element by its ref ID from a snapshot."""
    page = session.get_page(params["page_id"])
    ref = params["ref"].lstrip("@")
    text = params["text"]
    clear = params.get("clear", True)

    refs = session.get_refs(params["page_id"])
    if ref not in refs:
        return {"error": f"Ref @{ref} not found. Take a new snapshot first."}

    selector = refs[ref]["selector"]
    try:
        if clear:
            await page.fill(selector, "")
        await page.type(selector, text, delay=params.get("delay", 0))
        return {"status": "typed", "ref": f"@{ref}", "selector": selector, "length": len(text)}
    except Exception as e:
        return {"error": f"Failed to type into @{ref} ({selector}): {e}"}


# ---------------------------------------------------------------------------
# Console output capture
# ---------------------------------------------------------------------------

async def handle_get_console(session: BrowserSession, params: dict) -> dict:
    """Get console output (log/warn/error/info) captured from the page."""
    page_id = params["page_id"]
    clear = params.get("clear", False)

    messages = session.get_console_messages(page_id)

    if clear:
        session.clear_console_messages(page_id)

    return {
        "messages": messages[-100:],  # Last 100 messages
        "total": len(messages),
    }


# ---------------------------------------------------------------------------
# Browser lifecycle
# ---------------------------------------------------------------------------

async def handle_launch_browser(session: BrowserSession, params: dict) -> dict:
    """Launch a stealth CloakBrowser instance."""
    if session.is_running:
        return {"status": "Already running. Close first or use existing session.", "pages": session.list_pages()}

    # Clean up stale state if browser died but references linger
    if session._browser is not None or session._context is not None:
        logger.warning("Stale browser references detected on launch — cleaning up")
        session._force_cleanup()

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
        "status": "navigated",
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
    """Take a screenshot of the page or a specific element. Saves to disk for agent access."""
    page = session.get_page(params["page_id"])

    selector = params.get("selector")
    full_page = params.get("full_page", False)

    # Generate a file path
    timestamp = int(time.time() * 1000)
    filename = f"screenshot_{timestamp}.png"
    filepath = ARTIFACTS_DIR / filename

    if selector:
        locator = page.locator(selector)
        screenshot_bytes = await locator.screenshot()
    else:
        screenshot_bytes = await page.screenshot(full_page=full_page)

    # Save to disk so agents can use vision tools on the file
    filepath.write_bytes(screenshot_bytes)

    return {
        "path": str(filepath),
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
    """Generate a PDF of the current page. Saves to disk for agent access."""
    page = session.get_page(params["page_id"])

    pdf_kwargs = {}
    if "format" in params:
        pdf_kwargs["format"] = params["format"]
    if "print_background" in params:
        pdf_kwargs["print_background"] = params["print_background"]

    timestamp = int(time.time() * 1000)
    filename = f"page_{timestamp}.pdf"
    filepath = ARTIFACTS_DIR / filename

    pdf_bytes = await page.pdf(**pdf_kwargs)
    filepath.write_bytes(pdf_bytes)

    return {
        "path": str(filepath),
        "mime_type": "application/pdf",
        "size_bytes": len(pdf_bytes),
    }


# ---------------------------------------------------------------------------
# Agent-friendly content extraction
# ---------------------------------------------------------------------------

async def handle_get_text(session: BrowserSession, params: dict) -> dict:
    """Extract readable text content from the page, cleaned for agent consumption."""
    page = session.get_page(params["page_id"])
    selector = params.get("selector", "body")
    max_length = params.get("max_length", 50000)

    # Use innerText which gives rendered/visible text only
    text = await page.inner_text(selector)

    # Clean up excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = text.strip()

    truncated = len(text) > max_length
    if truncated:
        text = text[:max_length] + "\n\n[... truncated]"

    return {
        "text": text,
        "length": len(text),
        "truncated": truncated,
        "selector": selector,
    }


async def handle_get_links(session: BrowserSession, params: dict) -> dict:
    """Extract all links from the page with their text and URLs."""
    page = session.get_page(params["page_id"])
    selector = params.get("selector", "body")

    links = await page.evaluate(f"""
        (() => {{
            const container = document.querySelector('{selector}') || document.body;
            const anchors = container.querySelectorAll('a[href]');
            return Array.from(anchors).map(a => ({{
                text: a.innerText.trim().substring(0, 200),
                href: a.href,
                visible: a.offsetParent !== null
            }})).filter(l => l.text && l.visible);
        }})()
    """)

    return {
        "links": links[:500],
        "count": len(links),
    }


async def handle_get_form_fields(session: BrowserSession, params: dict) -> dict:
    """Extract all form fields from the page with their types, names, and values."""
    page = session.get_page(params["page_id"])
    selector = params.get("selector", "body")

    fields = await page.evaluate(f"""
        (() => {{
            const container = document.querySelector('{selector}') || document.body;
            const inputs = container.querySelectorAll('input, textarea, select, button[type="submit"]');
            return Array.from(inputs).map(el => {{
                const field = {{
                    tag: el.tagName.toLowerCase(),
                    type: el.type || '',
                    name: el.name || '',
                    id: el.id || '',
                    placeholder: el.placeholder || '',
                    value: el.value || '',
                    visible: el.offsetParent !== null,
                    required: el.required || false,
                }};
                if (el.tagName === 'SELECT') {{
                    field.options = Array.from(el.options).map(o => ({{
                        value: o.value,
                        text: o.text,
                        selected: o.selected
                    }}));
                }}
                if (el.id) field.selector = '#' + el.id;
                else if (el.name) field.selector = el.tagName.toLowerCase() + '[name="' + el.name + '"]';
                else field.selector = null;

                const label = el.labels && el.labels[0];
                if (label) field.label = label.innerText.trim();

                return field;
            }}).filter(f => f.visible);
        }})()
    """)

    return {
        "fields": fields,
        "count": len(fields),
    }


async def handle_smart_action(session: BrowserSession, params: dict) -> dict:
    """Perform a high-level action: click a link/button by its visible text.

    Tries multiple strategies to find the element, including text matching,
    ARIA roles, title attributes, and partial text matching.
    """
    page = session.get_page(params["page_id"])
    text = params["text"]
    action = params.get("action", "click")
    value = params.get("value", "")

    strategies = [
        ("exact_text", lambda: page.get_by_text(text, exact=True)),
        ("text_match", lambda: page.get_by_text(text, exact=False)),
        ("role_button", lambda: page.get_by_role("button", name=text)),
        ("role_link", lambda: page.get_by_role("link", name=text)),
        ("role_menuitem", lambda: page.get_by_role("menuitem", name=text)),
        ("role_tab", lambda: page.get_by_role("tab", name=text)),
        ("label", lambda: page.get_by_label(text)),
        ("placeholder", lambda: page.get_by_placeholder(text)),
        ("title", lambda: page.get_by_title(text)),
        ("alt_text", lambda: page.get_by_alt_text(text)),
    ]

    for strategy_name, get_locator in strategies:
        try:
            locator = get_locator()
            if await locator.count() > 0:
                if action == "click":
                    await locator.first.click(timeout=5000)
                    return {"status": "clicked", "matched_by": strategy_name, "text": text}
                elif action == "fill":
                    await locator.first.fill(value)
                    return {"status": "filled", "matched_by": strategy_name, "text": text}
                elif action == "type":
                    await locator.first.type(value)
                    return {"status": "typed", "matched_by": strategy_name, "text": text}
        except Exception:
            continue

    # Last resort: try CSS selector directly
    try:
        await page.click(f'[aria-label*="{text}" i]', timeout=3000)
        return {"status": "clicked", "matched_by": "aria_label_css", "text": text}
    except Exception:
        pass

    return {
        "status": "not_found",
        "text": text,
        "hint": "Element not found. Try snapshot() to see available interactive elements with ref IDs, then use click_ref().",
    }
