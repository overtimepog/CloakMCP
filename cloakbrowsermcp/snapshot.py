"""Accessibility tree snapshot extraction for CloakBrowser MCP v2."""

from __future__ import annotations

SNAPSHOT_JS = """
(() => {
  const FULL = !!window.__snapshot_full_mode;
  const MAX_DEPTH = 15;
  const TEXT_LIMIT = FULL ? 80 : 40;
  const MAX_OPTIONS = 5;

  // --- Loading state detection ---
  const loadingSelectors = '[aria-busy="true"], .loading, .skeleton, [data-loading], .spinner, .loader';
  const loadingEls = document.querySelectorAll(loadingSelectors);
  const loadingDetected = loadingEls.length > 0;

  // --- Detect top-layer / modal elements ---
  const MODAL_SELECTORS = [
    'dialog[open]', '[role="dialog"]', '[role="alertdialog"]',
    '[aria-modal="true"]', '.modal.show', '.modal.open',
    '.modal[style*="display: block"]', '.modal[style*="display:block"]',
    '[data-state="open"][role="dialog"]'
  ];
  function findModals() {
    const modals = [];
    for (const sel of MODAL_SELECTORS) {
      try { document.querySelectorAll(sel).forEach(m => { if (!modals.includes(m)) modals.push(m); }); }
      catch(e) {}
    }
    return modals;
  }

  // --- Visibility check (fixed for modals/fixed ancestors) ---
  function hasFixedOrStickyAncestor(el) {
    let cur = el.parentElement;
    while (cur && cur !== document.body && cur !== document.documentElement) {
      const pos = getComputedStyle(cur).position;
      if (pos === 'fixed' || pos === 'sticky' || pos === 'absolute') return true;
      cur = cur.parentElement;
    }
    return false;
  }

  function isVisible(el) {
    if (!el || el.nodeType !== 1) return false;
    if (el.offsetParent === null) {
      const pos = getComputedStyle(el).position;
      if (pos !== 'fixed' && pos !== 'sticky') {
        if (el.tagName !== 'BODY' && el.tagName !== 'HTML') {
          // Check if inside a fixed/absolute ancestor (common for modals)
          if (!hasFixedOrStickyAncestor(el)) return false;
        }
      }
    }
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    if (el.hasAttribute('hidden') && !el.matches('dialog[open]')) return false;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return false;
    return true;
  }

  // --- Interactive element detection ---
  const INTERACTIVE_SELECTORS = [
    'a[href]', 'button', 'input', 'select', 'textarea',
    '[role="button"]', '[role="link"]', '[role="checkbox"]', '[role="radio"]',
    '[role="tab"]', '[role="menuitem"]', '[role="switch"]', '[role="combobox"]',
    '[role="slider"]', '[role="spinbutton"]', '[role="textbox"]',
    '[tabindex]:not([tabindex="-1"])', '[contenteditable="true"]',
    '[onclick]', '[data-action]', 'summary', 'details > summary'
  ];

  function isInteractive(el) {
    return INTERACTIVE_SELECTORS.some(sel => {
      try { return el.matches(sel); } catch(e) { return false; }
    });
  }

  // --- Label association ---
  function getLabel(el) {
    // 1. aria-label
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');

    // 2. aria-labelledby
    const labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy) {
      const parts = labelledBy.split(/\\s+/).map(id => {
        const ref = document.getElementById(id);
        return ref ? ref.textContent.trim() : '';
      }).filter(Boolean);
      if (parts.length) return parts.join(' ');
    }

    // 3. for/id association
    if (el.id) {
      const labelEl = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (labelEl) return labelEl.textContent.trim();
    }

    // 4. Wrapping <label>
    const parentLabel = el.closest('label');
    if (parentLabel) {
      const clone = parentLabel.cloneNode(true);
      // Remove the input itself from the clone to get just the label text
      const inputs = clone.querySelectorAll('input,select,textarea');
      inputs.forEach(i => i.remove());
      const text = clone.textContent.trim();
      if (text) return text;
    }

    // 5. title attribute
    if (el.getAttribute('title')) return el.getAttribute('title');

    // 6. placeholder
    if (el.getAttribute('placeholder')) return el.getAttribute('placeholder');

    return '';
  }

  // --- CSS selector generation ---
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

  // --- Truncate text ---
  function truncText(str) {
    if (!str) return '';
    str = str.replace(/\\s+/g, ' ').trim();
    if (str.length > TEXT_LIMIT) return str.slice(0, TEXT_LIMIT - 1) + '\\u2026';
    return str;
  }

  // --- Refs collection ---
  const refs = {};
  let refCounter = 0;

  function addRef(el) {
    refCounter++;
    const key = 'e' + refCounter;
    refs[key] = {
      selector: getSelector(el),
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role') || ''
    };
    return key;
  }

  // --- Build snapshot tree ---
  const lines = [];

  function describeElement(el, depth) {
    if (depth > MAX_DEPTH) return;
    if (!isVisible(el)) return;

    const tag = el.tagName.toLowerCase();
    const indent = '  '.repeat(Math.min(depth, MAX_DEPTH));
    const role = el.getAttribute('role');
    const ariaExpanded = el.getAttribute('aria-expanded');
    const ariaChecked = el.getAttribute('aria-checked');
    const ariaSelected = el.getAttribute('aria-selected');
    const disabled = el.hasAttribute('disabled') || el.getAttribute('aria-disabled') === 'true';

    // Skip non-visible structural elements
    if (['script', 'style', 'noscript', 'template', 'svg', 'path'].includes(tag)) return;

    let isInt = isInteractive(el);
    let ref = '';
    if (isInt) {
      const key = addRef(el);
      ref = '[@' + key + ']';
    }

    // Detect loading state on element
    let loadingMark = '';
    try {
      if (el.matches(loadingSelectors)) loadingMark = ' [loading]';
    } catch(e) {}

    // Build description based on element type
    let desc = '';

    if (tag === 'input') {
      const type = (el.getAttribute('type') || 'text').toLowerCase();
      const label = getLabel(el);
      const val = el.value || '';
      const placeholder = el.getAttribute('placeholder') || '';
      if (type === 'checkbox' || type === 'radio') {
        const checked = el.checked ? '[x]' : '[ ]';
        desc = indent + ref + ' ' + checked + ' ' + (label || type) + loadingMark;
      } else {
        const display = val ? truncText(val) : (placeholder ? '(' + truncText(placeholder) + ')' : '');
        desc = indent + ref + ' input[' + type + '] ' + (label ? '"' + truncText(label) + '"' : '') + (display ? ': ' + display : '') + loadingMark;
      }
    } else if (tag === 'textarea') {
      const label = getLabel(el);
      const val = el.value || '';
      const placeholder = el.getAttribute('placeholder') || '';
      const display = val ? truncText(val) : (placeholder ? '(' + truncText(placeholder) + ')' : '');
      desc = indent + ref + ' textarea ' + (label ? '"' + truncText(label) + '"' : '') + (display ? ': ' + display : '') + loadingMark;
    } else if (tag === 'select') {
      const label = getLabel(el);
      const options = Array.from(el.options);
      const selected = el.selectedIndex >= 0 ? options[el.selectedIndex] : null;
      let optList = options.slice(0, MAX_OPTIONS).map(o => {
        const sel = o.selected ? '(*) ' : '';
        return sel + truncText(o.textContent);
      });
      if (options.length > MAX_OPTIONS) optList.push('... +' + (options.length - MAX_OPTIONS) + ' more');
      desc = indent + ref + ' select ' + (label ? '"' + truncText(label) + '"' : '') + (selected ? ' = ' + truncText(selected.textContent) : '') + loadingMark;
      if (FULL) {
        optList.forEach(o => lines.push(indent + '  ' + o));
      }
    } else if (tag === 'button' || role === 'button') {
      const text = truncText(el.textContent);
      desc = indent + ref + ' button "' + text + '"' + (disabled ? ' [disabled]' : '') + loadingMark;
    } else if (tag === 'a') {
      const text = truncText(el.textContent);
      const href = el.getAttribute('href') || '';
      const hrefDisplay = href.length > 50 ? href.slice(0, 47) + '...' : href;
      desc = indent + ref + ' link "' + text + '"' + (FULL ? ' -> ' + hrefDisplay : '') + loadingMark;
    } else if (tag === 'img') {
      const alt = el.getAttribute('alt') || '';
      desc = indent + 'img' + (alt ? ' "' + truncText(alt) + '"' : ' [no alt]') + loadingMark;
    } else if (['h1','h2','h3','h4','h5','h6'].includes(tag)) {
      desc = indent + tag + ' "' + truncText(el.textContent) + '"' + loadingMark;
    } else if (tag === 'nav') {
      desc = indent + 'nav' + (el.getAttribute('aria-label') ? ' "' + el.getAttribute('aria-label') + '"' : '') + loadingMark;
    } else if (tag === 'main' || role === 'main') {
      desc = indent + 'main' + loadingMark;
    } else if (tag === 'form') {
      desc = indent + 'form' + (el.getAttribute('aria-label') ? ' "' + el.getAttribute('aria-label') + '"' : '') + loadingMark;
    } else if (tag === 'table') {
      desc = indent + 'table' + loadingMark;
    } else if (tag === 'dialog' || role === 'dialog' || role === 'alertdialog') {
      const label = el.getAttribute('aria-label') || '';
      desc = indent + (ref || '') + ' dialog' + (label ? ' "' + truncText(label) + '"' : '') + loadingMark;
    } else if (role === 'tablist') {
      desc = indent + 'tablist' + loadingMark;
    } else if (role === 'tab') {
      const text = truncText(el.textContent);
      const sel = ariaSelected === 'true' ? ' [selected]' : '';
      desc = indent + ref + ' tab "' + text + '"' + sel + loadingMark;
    } else if (role === 'menu' || role === 'menubar') {
      desc = indent + role + loadingMark;
    } else if (role === 'menuitem') {
      desc = indent + ref + ' menuitem "' + truncText(el.textContent) + '"' + loadingMark;
    } else if (role === 'switch' || role === 'checkbox') {
      const checked = ariaChecked === 'true' ? '[x]' : '[ ]';
      const label = getLabel(el) || el.textContent.trim();
      desc = indent + ref + ' ' + checked + ' ' + truncText(label) + loadingMark;
    } else if (tag === 'details') {
      const open = el.hasAttribute('open') ? '[open]' : '[closed]';
      desc = indent + 'details ' + open + loadingMark;
    } else if (tag === 'summary') {
      desc = indent + ref + ' summary "' + truncText(el.textContent) + '"' + loadingMark;
    } else if (isInt) {
      desc = indent + ref + ' ' + tag + (role ? '[' + role + ']' : '') + ' "' + truncText(el.textContent) + '"' + loadingMark;
    }

    // Add aria-expanded info
    if (ariaExpanded !== null && desc) {
      desc += ariaExpanded === 'true' ? ' [expanded]' : ' [collapsed]';
    }

    if (desc) {
      lines.push(desc);
    }

    // For non-described container elements, check for text nodes
    if (!desc && !isInt) {
      // Only emit text for leaf-like elements or elements with direct text
      const directText = Array.from(el.childNodes)
        .filter(n => n.nodeType === 3 && n.textContent.trim())
        .map(n => truncText(n.textContent))
        .join(' ');
      if (directText && !['div','span','section','article','header','footer','li','ul','ol','td','th','tr','tbody','thead','p','dl','dt','dd'].includes(tag)) {
        lines.push(indent + '"' + directText + '"');
      } else if (directText && ['p','li','td','th','dt','dd','blockquote','figcaption','cite','label','legend'].includes(tag)) {
        lines.push(indent + truncText(el.textContent));
      }
    }

    // Recurse into children
    const children = el.children;
    for (let i = 0; i < children.length; i++) {
      describeElement(children[i], depth + (desc ? 1 : 0));
    }

    // Walk into shadow DOM
    if (el.shadowRoot) {
      const shadowChildren = el.shadowRoot.children;
      for (let i = 0; i < shadowChildren.length; i++) {
        describeElement(shadowChildren[i], depth + 1);
      }
    }

    // Handle iframes (same-origin only)
    if (tag === 'iframe') {
      try {
        const iframeDoc = el.contentDocument || el.contentWindow.document;
        if (iframeDoc && iframeDoc.body) {
          lines.push(indent + '  [iframe content]');
          describeElement(iframeDoc.body, depth + 1);
        }
      } catch(e) {
        lines.push(indent + '  [iframe: cross-origin]');
      }
    }
  }

  // --- Page header ---
  const title = document.title || '(no title)';
  const url = location.href;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const header = 'Page: ' + title + '\\nURL: ' + url + '\\nViewport: ' + vw + 'x' + vh + (loadingDetected ? '\\n[!] Loading detected' : '');
  lines.push(header);
  lines.push('---');

  // --- Prioritize modals/dialogs (render them FIRST) ---
  const modals = findModals();
  const modalSet = new Set(modals);
  const walkedModals = new Set();

  if (modals.length > 0) {
    lines.push('[Modal/Dialog]');
    for (const modal of modals) {
      describeElement(modal, 0);
      walkedModals.add(modal);
    }
    lines.push('[Page Content]');
  }

  // Walk the rest of the DOM, skipping already-rendered modals
  const origDescribe = describeElement;
  const oldDescribeElement = describeElement;

  // Use a flag to skip modal subtrees during main walk
  function describeElementSkipModals(el, depth) {
    if (walkedModals.has(el)) return;
    if (depth > MAX_DEPTH) return;
    if (!isVisible(el)) return;

    const tag = el.tagName.toLowerCase();
    const indent = '  '.repeat(Math.min(depth, MAX_DEPTH));
    const role = el.getAttribute('role');
    const ariaExpanded = el.getAttribute('aria-expanded');
    const ariaChecked = el.getAttribute('aria-checked');
    const ariaSelected = el.getAttribute('aria-selected');
    const disabled = el.hasAttribute('disabled') || el.getAttribute('aria-disabled') === 'true';

    if (['script', 'style', 'noscript', 'template', 'svg', 'path'].includes(tag)) return;

    let isInt = isInteractive(el);
    let ref = '';
    if (isInt) {
      const key = addRef(el);
      ref = '[@' + key + ']';
    }

    let loadingMark = '';
    try { if (el.matches(loadingSelectors)) loadingMark = ' [loading]'; } catch(e) {}

    let desc = '';

    if (tag === 'input') {
      const type = (el.getAttribute('type') || 'text').toLowerCase();
      const label = getLabel(el);
      const val = el.value || '';
      const placeholder = el.getAttribute('placeholder') || '';
      if (type === 'checkbox' || type === 'radio') {
        const checked = el.checked ? '[x]' : '[ ]';
        desc = indent + ref + ' ' + checked + ' ' + (label || type) + loadingMark;
      } else {
        const display = val ? truncText(val) : (placeholder ? '(' + truncText(placeholder) + ')' : '');
        desc = indent + ref + ' input[' + type + '] ' + (label ? '"' + truncText(label) + '"' : '') + (display ? ': ' + display : '') + loadingMark;
      }
    } else if (tag === 'textarea') {
      const label = getLabel(el);
      const val = el.value || '';
      const placeholder = el.getAttribute('placeholder') || '';
      const display = val ? truncText(val) : (placeholder ? '(' + truncText(placeholder) + ')' : '');
      desc = indent + ref + ' textarea ' + (label ? '"' + truncText(label) + '"' : '') + (display ? ': ' + display : '') + loadingMark;
    } else if (tag === 'select') {
      const label = getLabel(el);
      const options = Array.from(el.options);
      const selected = el.selectedIndex >= 0 ? options[el.selectedIndex] : null;
      let optList = options.slice(0, MAX_OPTIONS).map(o => { const sel = o.selected ? '(*) ' : ''; return sel + truncText(o.textContent); });
      if (options.length > MAX_OPTIONS) optList.push('... +' + (options.length - MAX_OPTIONS) + ' more');
      desc = indent + ref + ' select ' + (label ? '"' + truncText(label) + '"' : '') + (selected ? ' = ' + truncText(selected.textContent) : '') + loadingMark;
      if (FULL) { optList.forEach(o => lines.push(indent + '  ' + o)); }
    } else if (tag === 'button' || role === 'button') {
      desc = indent + ref + ' button "' + truncText(el.textContent) + '"' + (disabled ? ' [disabled]' : '') + loadingMark;
    } else if (tag === 'a') {
      const text = truncText(el.textContent);
      const href = el.getAttribute('href') || '';
      const hrefDisplay = href.length > 50 ? href.slice(0, 47) + '...' : href;
      desc = indent + ref + ' link "' + text + '"' + (FULL ? ' -> ' + hrefDisplay : '') + loadingMark;
    } else if (tag === 'img') {
      const alt = el.getAttribute('alt') || '';
      desc = indent + 'img' + (alt ? ' "' + truncText(alt) + '"' : ' [no alt]') + loadingMark;
    } else if (['h1','h2','h3','h4','h5','h6'].includes(tag)) {
      desc = indent + tag + ' "' + truncText(el.textContent) + '"' + loadingMark;
    } else if (tag === 'nav') {
      desc = indent + 'nav' + (el.getAttribute('aria-label') ? ' "' + el.getAttribute('aria-label') + '"' : '') + loadingMark;
    } else if (tag === 'main' || role === 'main') {
      desc = indent + 'main' + loadingMark;
    } else if (tag === 'form') {
      desc = indent + 'form' + (el.getAttribute('aria-label') ? ' "' + el.getAttribute('aria-label') + '"' : '') + loadingMark;
    } else if (tag === 'table') {
      desc = indent + 'table' + loadingMark;
    } else if (tag === 'dialog' || role === 'dialog' || role === 'alertdialog') {
      const label = el.getAttribute('aria-label') || '';
      desc = indent + (ref || '') + ' dialog' + (label ? ' "' + truncText(label) + '"' : '') + loadingMark;
    } else if (role === 'tablist') {
      desc = indent + 'tablist' + loadingMark;
    } else if (role === 'tab') {
      const text = truncText(el.textContent);
      const sel = ariaSelected === 'true' ? ' [selected]' : '';
      desc = indent + ref + ' tab "' + text + '"' + sel + loadingMark;
    } else if (role === 'menu' || role === 'menubar') {
      desc = indent + role + loadingMark;
    } else if (role === 'menuitem') {
      desc = indent + ref + ' menuitem "' + truncText(el.textContent) + '"' + loadingMark;
    } else if (role === 'switch' || role === 'checkbox') {
      const checked = ariaChecked === 'true' ? '[x]' : '[ ]';
      const label = getLabel(el) || el.textContent.trim();
      desc = indent + ref + ' ' + checked + ' ' + truncText(label) + loadingMark;
    } else if (tag === 'details') {
      const open = el.hasAttribute('open') ? '[open]' : '[closed]';
      desc = indent + 'details ' + open + loadingMark;
    } else if (tag === 'summary') {
      desc = indent + ref + ' summary "' + truncText(el.textContent) + '"' + loadingMark;
    } else if (isInt) {
      desc = indent + ref + ' ' + tag + (role ? '[' + role + ']' : '') + ' "' + truncText(el.textContent) + '"' + loadingMark;
    }

    if (ariaExpanded !== null && desc) {
      desc += ariaExpanded === 'true' ? ' [expanded]' : ' [collapsed]';
    }

    if (desc) lines.push(desc);

    if (!desc && !isInt) {
      const directText = Array.from(el.childNodes)
        .filter(n => n.nodeType === 3 && n.textContent.trim())
        .map(n => truncText(n.textContent))
        .join(' ');
      if (directText && !['div','span','section','article','header','footer','li','ul','ol','td','th','tr','tbody','thead','p','dl','dt','dd'].includes(tag)) {
        lines.push(indent + '"' + directText + '"');
      } else if (directText && ['p','li','td','th','dt','dd','blockquote','figcaption','cite','label','legend'].includes(tag)) {
        lines.push(indent + truncText(el.textContent));
      }
    }

    const children = el.children;
    for (let i = 0; i < children.length; i++) {
      describeElementSkipModals(children[i], depth + (desc ? 1 : 0));
    }

    if (el.shadowRoot) {
      const shadowChildren = el.shadowRoot.children;
      for (let i = 0; i < shadowChildren.length; i++) {
        describeElementSkipModals(shadowChildren[i], depth + 1);
      }
    }

    if (tag === 'iframe') {
      try {
        const iframeDoc = el.contentDocument || el.contentWindow.document;
        if (iframeDoc && iframeDoc.body) {
          lines.push(indent + '  [iframe content]');
          describeElementSkipModals(iframeDoc.body, depth + 1);
        }
      } catch(e) {
        lines.push(indent + '  [iframe: cross-origin]');
      }
    }
  }

  if (modals.length > 0) {
    describeElementSkipModals(document.body, 0);
  } else {
    describeElement(document.body, 0);
  }

  return {
    snapshot: lines.join('\\n'),
    refs: refs,
    interactiveCount: refCounter,
    loadingDetected: loadingDetected
  };
})()
"""


def _compress_snapshot(text: str, max_length: int) -> tuple[str, bool]:
    """Compress a snapshot by progressively removing non-interactive content.

    Strategy (applied in order until under max_length):
      1. Remove pure text lines (no [@eN] ref, no structural tag like h1/form/nav/table/dialog)
      2. Collapse consecutive blank lines
      3. Remove img lines without refs
      4. Hard truncate as last resort

    Returns:
        (compressed_text, was_compressed)
    """
    import re

    if len(text) <= max_length:
        return text, False

    lines = text.split("\n")

    # Find the header (first 3 lines: Page/URL/Viewport/---)
    header_end = 0
    for i, line in enumerate(lines):
        if line.strip() == "---":
            header_end = i + 1
            break
    header_lines = lines[:header_end]
    content_lines = lines[header_end:]

    # Ref pattern
    ref_pat = re.compile(r"\[@e\d+\]")
    # Structural tags worth keeping even without refs
    structural_pat = re.compile(
        r"^\s*(h[1-6]\s|form|nav|main|table|tablist|dialog|"
        r"\[Modal/Dialog\]|\[Page Content\]|\[iframe)"
    )

    # --- Pass 1: Remove pure text/decoration lines ---
    kept = []
    for line in content_lines:
        stripped = line.strip()
        if not stripped:
            kept.append(line)
            continue
        # Always keep lines with refs
        if ref_pat.search(line):
            kept.append(line)
            continue
        # Keep structural markers
        if structural_pat.match(stripped):
            kept.append(line)
            continue
        # Drop pure text lines (quoted strings, plain descriptions)
        # but keep them if we're still under budget — drop only as needed
        kept.append(line)

    result = "\n".join(header_lines + kept)
    if len(result) <= max_length:
        return result, False

    # --- Pass 2: Actually drop non-ref, non-structural lines ---
    kept2 = []
    for line in content_lines:
        stripped = line.strip()
        if not stripped:
            continue  # drop blank lines
        if ref_pat.search(line):
            kept2.append(line)
            continue
        if structural_pat.match(stripped):
            kept2.append(line)
            continue
        # Drop this line (pure text / img without ref / decoration)

    result = "\n".join(header_lines + kept2)
    if len(result) <= max_length:
        return result, True

    # --- Pass 3: Drop img lines without refs ---
    kept3 = [l for l in kept2 if not (l.strip().startswith("img") and not ref_pat.search(l))]
    result = "\n".join(header_lines + kept3)
    if len(result) <= max_length:
        return result, True

    # --- Pass 4: Hard truncate as last resort ---
    result = "\n".join(header_lines + kept3)
    if len(result) > max_length:
        result = result[:max_length] + "\n... [truncated]"
    return result, True


async def take_snapshot(
    page, page_id: str, session, full: bool = False, max_length: int = 12000
) -> dict:
    """Take an accessibility tree snapshot of the current page.

    Args:
        page: Playwright page object.
        page_id: Unique identifier for this page/tab.
        session: Session object with set_refs/get_refs methods.
        full: If True, include more detail (longer text, dropdown options).
        max_length: Maximum character length for the snapshot text.

    Returns:
        dict with keys: snapshot, interactive_elements, truncated, loading_detected
    """
    # Set mode flag on the page
    await page.evaluate(f"window.__snapshot_full_mode = {'true' if full else 'false'}")

    # Evaluate the snapshot JS
    result = await page.evaluate(SNAPSHOT_JS)

    snapshot_text = result.get("snapshot", "")
    refs = result.get("refs", {})
    interactive_count = result.get("interactiveCount", 0)
    loading_detected = result.get("loadingDetected", False)

    # Store refs in session
    session.set_refs(page_id, refs)

    # Smart compression: preserve interactive refs, drop decoration text first
    truncated = False
    if len(snapshot_text) > max_length:
        snapshot_text, was_compressed = _compress_snapshot(snapshot_text, max_length)
        truncated = was_compressed or len(snapshot_text) > max_length

    return {
        "snapshot": snapshot_text,
        "interactive_elements": interactive_count,
        "truncated": truncated,
        "loading_detected": loading_detected,
    }


def resolve_ref(session, page_id: str, ref: str) -> tuple[str, str]:
    """Resolve an element reference to a CSS selector.

    Args:
        session: Session object with get_refs method.
        page_id: Page identifier.
        ref: Element reference like '@e5' or 'e5'.

    Returns:
        Tuple of (clean_ref, css_selector).

    Raises:
        KeyError: If the reference is not found.
    """
    clean_ref = ref.lstrip("@").strip()
    refs = session.get_refs(page_id)
    if not refs or clean_ref not in refs:
        raise KeyError(
            f"Element reference '{clean_ref}' not found. "
            f"Take a new snapshot to get current element references."
        )
    entry = refs[clean_ref]
    selector = entry["selector"] if isinstance(entry, dict) else entry
    return clean_ref, selector
