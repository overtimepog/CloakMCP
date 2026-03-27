# CloakBrowserMCP

MCP server for [CloakBrowser](https://github.com/CloakHQ/CloakBrowser) — giving AI models full access to a stealth Chromium that passes every bot detection test.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

## What is this?

CloakBrowserMCP exposes [CloakBrowser](https://github.com/CloakHQ/CloakBrowser)'s stealth browser automation as an MCP (Model Context Protocol) server. Any AI model that speaks MCP can launch a source-level patched Chromium, navigate pages, interact with elements, take screenshots, and extract content — all while passing Cloudflare Turnstile, reCAPTCHA v3, FingerprintJS, and 30+ other detection services.

**CloakBrowser** is not a JS injection or config hack — it's a real Chromium binary with 33 C++ source-level patches. This MCP server wraps its full Python API into 21 tools that models can call directly.

## Install

```bash
pip install cloakbrowsermcp
```

Or from source:

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

### Run standalone

```bash
cloakbrowsermcp
```

## Tools

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

### Interaction

| Tool | Description |
|------|-------------|
| `click` | Click an element. With `humanize=True`, uses Bézier mouse curves. |
| `type_text` | Type with per-key events — better for reCAPTCHA than fill. |
| `fill_form` | Set a form field value directly. |
| `hover` | Hover over an element with realistic mouse movement. |
| `select_option` | Select from a `<select>` dropdown by value, label, or index. |
| `press_key` | Press keyboard keys (Enter, Tab, Escape, etc). |
| `scroll` | Scroll with realistic acceleration curves when humanized. |

### Content & Data

| Tool | Description |
|------|-------------|
| `screenshot` | Capture full page, viewport, or element screenshots (base64 PNG). |
| `get_content` | Extract HTML, visible text, or outer HTML from a selector. |
| `evaluate` | Run JavaScript in the page context and return results. |
| `wait_for_selector` | Wait for elements to appear, disappear, attach, or detach. |
| `get_cookies` | Get all cookies from the browser context. |
| `set_cookies` | Set cookies in the browser context. |
| `get_page_info` | Get current URL and title. |
| `pdf` | Generate a PDF of the page. |

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
│  AI Model   │ ◄──────────────────► │  CloakBrowserMCP  │
│ (Claude,    │    stdio / HTTP       │                  │
│  GPT, etc)  │                       │  21 tools        │
└─────────────┘                       │  session mgmt    │
                                      │  page tracking   │
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

- **`cloakbrowsermcp/server.py`** — MCP server with all tool registrations
- **`cloakbrowsermcp/session.py`** — Browser lifecycle & page management
- **`cloakbrowsermcp/tools.py`** — Core tool handlers (navigate, click, type, screenshot, etc.)
- **`cloakbrowsermcp/tools_advanced.py`** — Stealth config, network interception, viewport, media emulation

## Development

```bash
git clone https://github.com/overtimepog/CloakMCP.git
cd CloakMCP
pip install -e ".[dev]"

# Run tests (80 tests, all mocked — no browser needed)
pytest

# Run tests with verbose output
pytest -v
```

## License

MIT — see [LICENSE](LICENSE).

## Credits

Built on [CloakBrowser](https://github.com/CloakHQ/CloakBrowser) by CloakHQ and the [Model Context Protocol](https://modelcontextprotocol.io) Python SDK.
