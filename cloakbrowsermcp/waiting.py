"""Smart waiting and retry logic for CloakBrowser MCP v2."""

import asyncio

SETTLE_JS = """
() => new Promise((resolve) => {
    let mutations = 0;
    let timer = null;
    const start = Date.now();
    const maxTimeout = __TIMEOUT_MS__;

    const done = (settled) => {
        observer.disconnect();
        resolve({
            settled: settled,
            mutations: mutations,
            elapsed_ms: Date.now() - start
        });
    };

    const resetTimer = () => {
        if (timer) clearTimeout(timer);
        timer = setTimeout(() => done(true), 500);
    };

    const observer = new MutationObserver((records) => {
        mutations += records.length;
        resetTimer();
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        characterData: true
    });

    // Start the settle timer immediately
    resetTimer();

    // Hard cap at max timeout
    setTimeout(() => done(false), maxTimeout);
})
"""

LOADING_DETECT_JS = """
() => {
    const indicators = [];

    document.querySelectorAll('[aria-busy="true"]').forEach(el => {
        indicators.push('aria-busy: ' + (el.tagName.toLowerCase() + (el.id ? '#' + el.id : '')));
    });

    const loadingClasses = ['loading', 'spinner', 'skeleton', 'shimmer'];
    for (const cls of loadingClasses) {
        document.querySelectorAll('.' + cls).forEach(el => {
            indicators.push('class.' + cls + ': ' + el.tagName.toLowerCase());
        });
    }

    document.querySelectorAll('[data-loading]').forEach(el => {
        indicators.push('data-loading: ' + el.tagName.toLowerCase());
    });

    return { loading: indicators.length > 0, indicators: indicators };
}
"""


async def wait_for_settle(page, timeout_ms: int = 5000) -> dict:
    """Wait for DOM to settle (no mutations for 500ms)."""
    js = SETTLE_JS.replace("__TIMEOUT_MS__", str(timeout_ms))
    try:
        result = await page.evaluate(js)
        return result
    except Exception:
        return {"settled": False, "mutations": 0, "elapsed_ms": timeout_ms}


async def smart_navigate(page, url: str, timeout: int = 30000) -> dict:
    """Navigate to URL and wait for page to settle."""
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout)

    title = await page.title()

    # Cloudflare-like challenge detection
    challenge_keywords = ["checking", "just a moment"]
    if any(kw in title.lower() for kw in challenge_keywords):
        await asyncio.sleep(1.5)

    settle = await wait_for_settle(page)

    # Re-read in case title changed after settle
    title = await page.title()
    current_url = page.url

    return {"url": current_url, "title": title, "settled": settle["settled"]}


async def retry_action(action_fn, max_retries: int = 1):
    """Call action_fn with retries on failure."""
    last_error = None
    for attempt in range(1 + max_retries):
        try:
            return await action_fn()
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                await asyncio.sleep(0.5)
    raise last_error


async def detect_loading(page) -> dict:
    """Check for common loading indicators on the page."""
    try:
        return await page.evaluate(LOADING_DETECT_JS)
    except Exception:
        return {"loading": False, "indicators": []}
