"""Annotated screenshot capture for CloakBrowser MCP v2."""

from __future__ import annotations

import time
from pathlib import Path

ANNOTATE_JS = """
(() => {
  // --- Interactive element detection (mirrors snapshot.py) ---
  const INTERACTIVE_SELECTORS = [
    'a[href]', 'button', 'input', 'select', 'textarea',
    '[role="button"]', '[role="link"]', '[role="checkbox"]', '[role="radio"]',
    '[role="tab"]', '[role="menuitem"]', '[role="switch"]', '[role="combobox"]',
    '[role="slider"]', '[role="spinbutton"]', '[role="textbox"]',
    '[tabindex]:not([tabindex="-1"])', '[contenteditable="true"]',
    '[onclick]', '[data-action]', 'summary'
  ];

  function isVisible(el) {
    if (!el || el.nodeType !== 1) return false;
    if (el.offsetParent === null && getComputedStyle(el).position !== 'fixed' && getComputedStyle(el).position !== 'sticky') {
      if (el.tagName !== 'BODY' && el.tagName !== 'HTML') return false;
    }
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    if (el.hasAttribute('hidden')) return false;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return false;
    return true;
  }

  function getSelector(el) {
    if (el.id) return '#' + CSS.escape(el.id);
    const parts = [];
    let cur = el;
    for (let i = 0; i < 4 && cur && cur !== document.body; i++) {
      let seg = cur.tagName.toLowerCase();
      if (cur.id) {
        seg = '#' + CSS.escape(cur.id);
        parts.unshift(seg);
        break;
      }
      if (cur.className && typeof cur.className === 'string') {
        const cls = cur.className.trim().split(/\\s+/).slice(0, 2).map(c => '.' + CSS.escape(c)).join('');
        seg += cls;
      }
      const parent = cur.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter(c => c.tagName === cur.tagName);
        if (siblings.length > 1) {
          const idx = siblings.indexOf(cur) + 1;
          seg += ':nth-of-type(' + idx + ')';
        }
      }
      parts.unshift(seg);
      cur = parent;
    }
    return parts.join(' > ');
  }

  // --- Color palette ---
  const COLORS = [
    { border: 'rgba(255, 0, 0, 0.7)',   bg: 'rgba(255, 0, 0, 0.85)',   text: '#fff' },
    { border: 'rgba(0, 128, 255, 0.7)',  bg: 'rgba(0, 128, 255, 0.85)', text: '#fff' },
    { border: 'rgba(0, 180, 0, 0.7)',    bg: 'rgba(0, 180, 0, 0.85)',   text: '#fff' },
    { border: 'rgba(200, 100, 0, 0.7)',  bg: 'rgba(200, 100, 0, 0.85)', text: '#fff' },
    { border: 'rgba(150, 0, 200, 0.7)',  bg: 'rgba(150, 0, 200, 0.85)', text: '#fff' },
    { border: 'rgba(0, 180, 180, 0.7)',  bg: 'rgba(0, 180, 180, 0.85)', text: '#fff' },
    { border: 'rgba(200, 0, 100, 0.7)',  bg: 'rgba(200, 0, 100, 0.85)', text: '#fff' },
    { border: 'rgba(100, 100, 0, 0.7)',  bg: 'rgba(100, 100, 0, 0.85)', text: '#fff' },
  ];

  // --- Find all interactive elements ---
  const allElements = [];
  const seen = new Set();

  INTERACTIVE_SELECTORS.forEach(sel => {
    try {
      document.querySelectorAll(sel).forEach(el => {
        if (!seen.has(el) && isVisible(el)) {
          seen.add(el);
          allElements.push(el);
        }
      });
    } catch(e) {}
  });

  // --- Create overlays ---
  const container = document.createElement('div');
  container.id = '__cloak_annotations__';
  container.style.cssText = 'position:absolute;top:0;left:0;width:0;height:0;overflow:visible;z-index:2147483647;pointer-events:none;';
  document.body.appendChild(container);

  const refs = {};
  let count = 0;

  allElements.forEach((el, idx) => {
    const rect = el.getBoundingClientRect();
    const scrollX = window.scrollX || document.documentElement.scrollLeft;
    const scrollY = window.scrollY || document.documentElement.scrollTop;

    // Skip off-screen elements with zero dimensions
    if (rect.width < 2 || rect.height < 2) return;

    count++;
    const refKey = 'e' + count;
    const color = COLORS[(count - 1) % COLORS.length];

    // Bounding box overlay
    const box = document.createElement('div');
    box.style.cssText = 'position:absolute;pointer-events:none;' +
      'left:' + (rect.left + scrollX - 2) + 'px;' +
      'top:' + (rect.top + scrollY - 2) + 'px;' +
      'width:' + (rect.width + 4) + 'px;' +
      'height:' + (rect.height + 4) + 'px;' +
      'border:2px solid ' + color.border + ';' +
      'border-radius:3px;' +
      'box-sizing:border-box;';
    container.appendChild(box);

    // Label
    const label = document.createElement('div');
    label.textContent = String(count);
    label.style.cssText = 'position:absolute;pointer-events:none;' +
      'left:' + (rect.left + scrollX - 2) + 'px;' +
      'top:' + (rect.top + scrollY - 18) + 'px;' +
      'background:' + color.bg + ';' +
      'color:' + color.text + ';' +
      'font-size:11px;font-weight:bold;font-family:monospace;' +
      'padding:1px 4px;border-radius:3px 3px 0 0;' +
      'line-height:14px;white-space:nowrap;';
    container.appendChild(label);

    refs[refKey] = {
      selector: getSelector(el),
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role') || ''
    };
  });

  return {
    element_count: count,
    refs: refs
  };
})()
"""

REMOVE_ANNOTATIONS_JS = """
(() => {
  const container = document.getElementById('__cloak_annotations__');
  if (container) container.remove();
})()
"""

# Artifacts directory
ARTIFACTS_DIR = Path.home() / ".cloakbrowser" / "artifacts"


async def take_annotated_screenshot(
    page, page_id: str, session, full_page: bool = False
) -> dict:
    """Take a screenshot with interactive elements annotated with numbered overlays.

    Args:
        page: Playwright page object.
        page_id: Unique identifier for this page/tab.
        session: Session object with set_refs/get_refs methods.
        full_page: If True, capture the full scrollable page.

    Returns:
        dict with keys: path, mime_type, size_bytes, element_count
    """
    # Ensure artifacts directory exists
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    # Inject annotations
    result = await page.evaluate(ANNOTATE_JS)
    element_count = result.get("element_count", 0)
    refs = result.get("refs", {})

    # Take screenshot
    timestamp = int(time.time() * 1000)
    filename = f"annotated_{timestamp}.png"
    filepath = ARTIFACTS_DIR / filename

    await page.screenshot(path=str(filepath), full_page=full_page)

    # Remove annotations
    await page.evaluate(REMOVE_ANNOTATIONS_JS)

    # Store refs in session
    session.set_refs(page_id, refs)

    # Get file size
    size_bytes = filepath.stat().st_size

    return {
        "path": str(filepath),
        "mime_type": "image/png",
        "size_bytes": size_bytes,
        "element_count": element_count,
    }
