# CloakBrowserMCP

MCP server for [CloakBrowser](https://github.com/CloakHQ/CloakBrowser) — giving AI agents full access to a stealth Chromium that passes every bot detection test.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

## What is this?

CloakBrowserMCP exposes [CloakBrowser](https://github.com/CloakHQ/CloakBrowser)'s stealth browser automation as an MCP (Model Context Protocol) server. Any AI agent that speaks MCP can launch a source-level patched Chromium, navigate pages, interact with elements, take screenshots, and extract content — all while passing Cloudflare Turnstile, reCAPTCHA v3, FingerprintJS, and 30+ other detection services.

**CloakBrowser** is not a JS injection or config hack — it's a real Chromium binary with 33 C++ source-level patches. This MCP server wraps its full Python API into agent-optimized tools with snapshot-based navigation.

## Install

**One-line setup** (clones, installs, downloads the stealth binary, runs tests):

```bash
curl -fsSL https://raw.githubusercontent.com/overtimepog/CloakMCP/main/setup.sh | bash
```

**pip install:**

```bash
pip install cloakbrowsermcp
```

**From source:**

```bash
git clone https://github.com/overtimepog/CloakMCP.git
cd CloakMCP
pip install -e ".[dev]"
```

## Quick Start

### Claude Desktop / Claude Code

Add to your MCP config:

```json
{
  "mcpServers": {
    "cloakbrowser": {
      "command": "cloakbrowsermcp"
    }
  }
}
```

### Hermes Agent

Add to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  cloakbrowser:
    command: "cloakbrowsermcp"
```

Tools will be available as `mcp_cloakbrowser_*` (e.g. `mcp_cloakbrowser_launch_browser`, `mcp_cloakbrowser_snapshot`).

### Run standalone

```bash
cloakbrowsermcp
```

## Agent Workflow — Snapshot + Refs

The recommended workflow for AI agents is **snapshot-based navigation**:

```
1. launch_browser()          → get page_id
2. navigate(page_id, url)    → go to a URL
3. snapshot(page_id)         → see interactive elements with [@eN] ref IDs
4. click_ref(page_id, '@e5') → click element by ref ID
5. type_ref(page_id, '@e3', 'text') → type into input by ref ID
6. get_text(page_id)         → read page content
7. close_browser()           → clean up
```

The `snapshot()` tool returns an accessibility-tree-like view:

```
Page: Example Login
URL: https://example.com/login
---
[@e1] text input "Email" placeholder="you@example.com"
[@e2] password input "Password"
[@e3] checkbox "Remember me" [unchecked]
[@e4] button "Sign In"
[@e5] link "Forgot password?" -> https://example.com/reset
```

Use `click_ref('@e4')` to click Sign In, `type_ref('@e1', 'user@example.com')` to fill email, etc. This is much more reliable than CSS selectors.

## Tools

### Snapshot & Ref-Based Navigation (Recommended)

| Tool | Description |
|------|-------------|
| `snapshot` | Get interactive elements with `[@eN]` ref IDs. The primary tool for understanding page structure. `full=True` includes text content. |
| `click_ref` | Click an element by its `[@eN]` ref from a snapshot. |
| `type_ref` | Type text into an input by its `[@eN]` ref. Clears field first by default. |

### Browser Lifecycle

| Tool | Description |
|------|-------------|
| `launch_browser` | Launch stealth Chromium with anti-detection. Supports proxy, humanize, persistent profiles, fingerprint seeds, timezone/locale, and custom viewport. |
| `close_browser` | Close the browser and all pages. |

### Page Management

| Tool | Description |
|------|-------------|
| `new_page` | Open a new tab, optionally navigating to a URL. |
| `close_page` | Close a specific page by ID. |
| `list_pages` | List all open pages with IDs and URLs. |

### Navigation

| Tool | Description |
|------|-------------|
| `navigate` | Go to a URL with configurable wait strategy and timeout. |
| `go_back` | Navigate back in page history. |
| `go_forward` | Navigate forward in page history. |
| `reload` | Reload the current page. |
| `wait_for_navigation` | Wait for a specific load state after an action. |

### Interaction

| Tool | Description |
|------|-------------|
| `smart_action` | Click/fill by visible text — 10 matching strategies, no CSS selector needed. |
| `click` | Click by CSS selector (prefer `click_ref` instead). |
| `type_text` | Type with per-key events (prefer `type_ref` instead). |
| `fill_form` | Set a form field value directly. |
| `hover` | Hover over an element with realistic mouse movement. |
| `select_option` | Select from a `<select>` dropdown by value, label, or index. |
| `press_key` | Press keyboard keys (Enter, Tab, Escape, etc). |
| `scroll` | Scroll with realistic acceleration curves when humanized. |

### Content & Data

| Tool | Description |
|------|-------------|
| `get_text` | Get clean readable text from the page (no HTML). Primary content reading tool. |
| `get_links` | Get all visible links with text and URLs. |
| `get_form_fields` | Discover all form inputs with types, names, labels, and CSS selectors. |
| `screenshot` | Capture screenshots — saves PNG to disk, returns file path. |
| `get_content` | Get raw HTML (prefer `get_text` for agents). |
| `evaluate` | Run JavaScript in the page context. |
| `wait_for_selector` | Wait for elements to appear/disappear. |
| `get_console` | Get browser console output and JS errors. |
| `get_cookies` / `set_cookies` | Manage browser cookies. |
| `get_page_info` | Get current URL and title. |
| `pdf` | Generate a PDF of the page. |

### Advanced

| Tool | Description |
|------|-------------|
| `network_intercept` | Block, mock, or log network requests by URL pattern. |
| `network_continue` | Remove a network interception route. |
| `set_viewport` | Change viewport size. |
| `emulate_media` | Emulate color scheme, media type, reduced motion. |
| `add_init_script` | Inject JS that runs before every page load. |
| `stealth_config` | Show current stealth configuration. |
| `binary_info` | Get CloakBrowser binary version and features. |

## Key Features

### Anti-Detection Stealth

Every browser session uses CloakBrowser's source-level patches:

- **33 C++ patches** — canvas, WebGL, audio, fonts, GPU, screen, automation signals
- **0.9 reCAPTCHA v3 score** — human-level, server-verified
- **Passes Cloudflare Turnstile**, FingerprintJS, BrowserScan, and 30+ detection services
- **`navigator.webdriver = false`** at the source level

### Human-Like Behavior

```
launch_browser(humanize=True)
```

One flag makes all interactions behave like a real user:
- Mouse: Bézier curves with easing and slight overshoot
- Keyboard: per-character timing, thinking pauses, occasional typos
- Scroll: accelerate → cruise → decelerate micro-steps

### Persistent Profiles

```
launch_browser(user_data_dir="./my-profile")
```

Cookies, localStorage, and cache persist across sessions. Bypasses incognito detection.

### Fingerprint Pinning

```
launch_browser(fingerprint_seed="42069")
```

Same seed = same fingerprint across launches. Look like a returning visitor instead of a new device each time.

### Proxy Support

```
launch_browser(proxy="http://user:pass@proxy:8080", geoip=True)
```

Auto-detects timezone and locale from the proxy IP.

## Architecture

```
┌─────────────┐     MCP Protocol      ┌──────────────────┐
│  AI Agent   │ ◄──────────────────► │  CloakBrowserMCP  │
│ (Claude,    │    stdio / HTTP       │                  │
│  Hermes,    │                       │  30 tools        │
│  GPT, etc)  │                       │  snapshot + refs  │
└─────────────┘                       │  console capture  │
                                      └────────┬─────────┘
                                               │
                                      ┌────────▼─────────┐
                                      │   CloakBrowser    │
                                      │                  │
                                      │  Patched Chromium │
                                      │  33 C++ patches   │
                                      │  Playwright API   │
                                      └──────────────────┘
```

- **`cloakbrowsermcp/server.py`** — MCP server with all tool registrations (server name: `cloakbrowser`)
- **`cloakbrowsermcp/session.py`** — Browser lifecycle, page management, ref storage, console capture
- **`cloakbrowsermcp/tools.py`** — Core tool handlers including snapshot, click_ref, type_ref, console
- **`cloakbrowsermcp/tools_advanced.py`** — Stealth config, network interception, viewport, media emulation

## MCP Naming Convention

When used with MCP clients like Hermes Agent, tools are prefixed with `mcp_{server_name}_`:

- Server name: `cloakbrowser`
- Tool `snapshot` → `mcp_cloakbrowser_snapshot`
- Tool `click_ref` → `mcp_cloakbrowser_click_ref`
- Tool `launch_browser` → `mcp_cloakbrowser_launch_browser`

This avoids name collisions with built-in tools and other MCP servers.

## Development

```bash
git clone https://github.com/overtimepog/CloakMCP.git
cd CloakMCP
pip install -e ".[dev]"

# Run tests (all mocked — no browser needed)
pytest

# Run tests with verbose output
pytest -v
```

## License

MIT — see [LICENSE](LICENSE).

## Credits

Built on [CloakBrowser](https://github.com/CloakHQ/CloakBrowser) by CloakHQ and the [Model Context Protocol](https://modelcontextprotocol.io) Python SDK.
