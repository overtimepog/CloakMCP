# CloakBrowser MCP

<!-- mcp-name: io.github.overtimepog/CloakMCP -->

**Stealth browser automation for AI agents** — a [Model Context Protocol](https://modelcontextprotocol.io) server combining CloakBrowser's anti-detection with Playwright MCP-inspired architecture.

CloakBrowser is a source-level patched Chromium that passes Cloudflare Turnstile, reCAPTCHA v3 (0.9 score), FingerprintJS, BrowserScan, and 30+ bot detection services.

## Why CloakBrowser MCP?

| Feature | Playwright MCP | CloakBrowser MCP |
|---------|---------------|-----------------|
| Anti-detection | ❌ None | ✅ Source-patched Chromium |
| Cloudflare bypass | ❌ | ✅ |
| reCAPTCHA v3 | ❌ | ✅ 0.9 score |
| Snapshot-first | ✅ | ✅ |
| Markdown extraction | ❌ | ✅ Readability-style |
| Annotated screenshots | ❌ | ✅ browser-use style |
| Smart page settling | Basic | ✅ MutationObserver + networkidle |
| Auto-retry clicks | ❌ | ✅ |
| Humanized input | ❌ | ✅ Mouse curves, keyboard timing |
| Capability gating | ✅ --caps | ✅ --caps |

## Quick Start

### Install

```bash
pip install cloakbrowsermcp
```

### Use with Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "cloakbrowser": {
      "command": "cloakbrowsermcp"
    }
  }
}
```

### Use with VS Code / Cursor

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "cloakbrowser": {
      "command": "cloakbrowsermcp",
      "args": ["--caps", "all"]
    }
  }
}
```

### Use with Hermes Agent

Add to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  cloakbrowser:
    command: cloakbrowsermcp
    args: ["--caps", "all"]
    timeout: 120
```

## How It Works

### Snapshot-First Architecture

CloakBrowser MCP uses **accessibility tree snapshots** as the primary way for AI models to understand web pages — not screenshots, not raw HTML.

```
1. cloak_launch()           → Start stealth browser
2. cloak_navigate(pid, url) → Go to page (auto-waits for settle)
3. cloak_snapshot(pid)      → Get interactive elements with [@eN] refs
4. cloak_click(pid, '@e5')  → Click element by ref
5. cloak_type(pid, '@e3', 'hello')  → Type into input
6. cloak_read_page(pid)     → Get content as clean markdown
7. cloak_close()            → Done
```

Each interactive element gets a `[@eN]` ref ID. All interaction tools use these refs — no CSS selectors needed.

### Three Ways to See a Page

1. **`cloak_snapshot()`** — Accessibility tree with `[@eN]` refs. Fast, cheap, reliable. **Use this.**
2. **`cloak_read_page()`** — Clean markdown extraction. For reading content, not interacting.
3. **`cloak_screenshot()`** — Annotated screenshot with element indices. For visual context (images, charts, CAPTCHAs).

### Stealth by Default

All anti-detection features are **ON by default**:
- Source-patched Chromium binary (not Playwright patches — actual Chromium source modifications)
- Human-like mouse curves, keyboard timing, and scroll patterns (`humanize=True`)
- Stealth fingerprint arguments (consistent canvas, WebGL, audio fingerprints)
- Proxy support with GeoIP-based timezone/locale detection

## Tools

### Core Tools (20 — always available)

| Tool | Description |
|------|-------------|
| `cloak_launch` | Start stealth browser (all anti-detection ON) |
| `cloak_close` | Close browser and release resources |
| `cloak_snapshot` | **PRIMARY** — accessibility tree with `[@eN]` refs |
| `cloak_click` | Click element by ref (auto-retry) |
| `cloak_type` | Type into input by ref (with submit option) |
| `cloak_select` | Select dropdown option by ref |
| `cloak_hover` | Hover over element by ref |
| `cloak_check` | Check/uncheck checkbox by ref |
| `cloak_read_page` | Page content as clean markdown |
| `cloak_screenshot` | Annotated screenshot with element indices |
| `cloak_navigate` | Go to URL (auto-waits for settle) |
| `cloak_back` | Navigate back in history |
| `cloak_forward` | Navigate forward in history |
| `cloak_press_key` | Press keyboard key |
| `cloak_scroll` | Scroll page up/down |
| `cloak_wait` | Wait for page to settle |
| `cloak_evaluate` | Execute JavaScript in page |
| `cloak_new_page` | Open new page/tab |
| `cloak_list_pages` | List all open pages |
| `cloak_close_page` | Close a specific page |

### Capability-Gated Tools (enabled via `--caps`)

Enable with `cloakbrowsermcp --caps network,cookies,pdf,console` or `--caps all`.

| Tool | Capability | Description |
|------|-----------|-------------|
| `cloak_network_intercept` | network | Block/mock/passthrough requests |
| `cloak_network_continue` | network | Remove interception rule |
| `cloak_get_cookies` | cookies | Get all cookies |
| `cloak_set_cookies` | cookies | Set cookies |
| `cloak_pdf` | pdf | Save page as PDF |
| `cloak_console` | console | Get browser console output |

## Configuration

### CLI Options

```
cloakbrowsermcp [--caps CAPS] [--transport {stdio,sse}] [--port PORT]
```

- `--caps`: Comma-separated capabilities: `network`, `cookies`, `pdf`, `console`, `all`
- `--transport`: MCP transport — `stdio` (default) or `sse`
- `--port`: Port for SSE transport (default: 8931)

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CLOAKBROWSER_LOG_LEVEL` | `INFO` | Log level |
| `CLOAKBROWSER_LOG_FILE` | `~/.cloakbrowser/logs/server.log` | Log file path |
| `CLOAKBROWSER_LOG_STDERR` | `false` | Also log to stderr |

### Launch Options

```python
cloak_launch(
    headless=True,        # False for headed mode (some sites require it)
    proxy="http://...",   # Residential proxy recommended
    humanize=True,        # Human-like input (ON by default)
    stealth_args=True,    # Stealth fingerprints (ON by default)
    timezone="America/New_York",
    locale="en-US",
    geoip=False,          # Auto-detect from proxy IP
    fingerprint_seed="my-identity",  # Consistent fingerprint across sessions
    user_data_dir="/path",  # Persistent profile
)
```

## Architecture

```
cloakbrowsermcp/
├── server.py      # FastMCP server, tool registration, error handling
├── session.py     # Browser lifecycle, page management, ref storage
├── snapshot.py    # Accessibility tree JS, ref resolution
├── markdown.py    # Readability-style HTML-to-markdown extraction
├── vision.py      # Annotated screenshots with element indices
├── waiting.py     # Smart wait, page settle, retry logic
├── stealth.py     # Stealth config inspection
├── network.py     # Network intercept, cookies (capability-gated)
├── __init__.py
└── __main__.py
```

### Design Principles

1. **Snapshot-first** — Tool descriptions steer models to use `cloak_snapshot()` as the primary page understanding tool
2. **Ref-based only** — No CSS selector tools. All interaction via `[@eN]` refs from snapshots
3. **Stealth by default** — Anti-detection, humanization, and stealth args all ON without configuration
4. **Auto-snapshot after actions** — Click, type, navigate all return an updated snapshot
5. **Smart waiting** — Auto-wait on navigation (networkidle + MutationObserver settle), auto-retry on failed clicks
6. **Capability gating** — Advanced tools (network, cookies, PDF) off by default to keep tool count low
7. **Clean content extraction** — Markdown for reading, snapshot for interaction, annotated screenshots for vision

## Development

```bash
git clone https://github.com/overtimepog/CloakMCP
cd CloakMCP
pip install -e ".[dev]"
pytest
```

## License

Apache-2.0
