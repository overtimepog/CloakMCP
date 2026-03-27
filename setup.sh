#!/usr/bin/env bash
set -euo pipefail

# CloakBrowserMCP — one-command setup
# Usage: curl -fsSL https://raw.githubusercontent.com/overtimepog/CloakMCP/main/setup.sh | bash

REPO="https://github.com/overtimepog/CloakMCP.git"
INSTALL_DIR="${CLOAKMCP_DIR:-$HOME/.cloakbrowsermcp}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail()  { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║        CloakBrowserMCP Setup             ║${NC}"
echo -e "${BOLD}║  Stealth browser automation for AI       ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""

# ─── Check Python ───────────────────────────────────────────────────────
info "Checking Python..."
PYTHON=""
for cmd in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
        major=$("$cmd" -c "import sys; print(sys.version_info.major)" 2>/dev/null || echo 0)
        minor=$("$cmd" -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo 0)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            ok "Found $cmd ($ver)"
            break
        else
            warn "$cmd is $ver (need 3.10+), skipping"
        fi
    fi
done
[ -z "$PYTHON" ] && fail "Python 3.10+ is required. Install from https://python.org/downloads/"

# ─── Check git ──────────────────────────────────────────────────────────
info "Checking git..."
command -v git &>/dev/null || fail "git not found. Install from https://git-scm.com/"
ok "git available"

# ─── Clone or update ───────────────────────────────────────────────────
if [ -d "$INSTALL_DIR/.git" ]; then
    info "Updating existing install at $INSTALL_DIR..."
    cd "$INSTALL_DIR"
    git pull origin main --quiet
    ok "Updated to latest"
else
    info "Cloning CloakBrowserMCP to $INSTALL_DIR..."
    git clone --quiet "$REPO" "$INSTALL_DIR"
    ok "Cloned"
fi

cd "$INSTALL_DIR"

# ─── Create venv ────────────────────────────────────────────────────────
VENV_DIR="$INSTALL_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    info "Creating virtual environment..."
    "$PYTHON" -m venv "$VENV_DIR"
    ok "venv created at $VENV_DIR"
else
    ok "venv already exists"
fi

# Activate venv for the rest of the script
source "$VENV_DIR/bin/activate"
PYTHON="python"  # now points to the venv python

# ─── Install package ───────────────────────────────────────────────────
info "Installing cloakbrowsermcp and dependencies..."
"$PYTHON" -m pip install --upgrade pip --quiet 2>&1 | grep -v "^\[notice\]" || true
"$PYTHON" -m pip install -e ".[dev]" --quiet 2>&1 | grep -v "^\[notice\]" || true
ok "Package installed"

# ─── Download CloakBrowser binary ──────────────────────────────────────
info "Downloading CloakBrowser stealth binary (~200MB, cached)..."
if "$PYTHON" -c "from cloakbrowser.download import ensure_binary; ensure_binary()" 2>&1; then
    ok "CloakBrowser binary ready"
else
    warn "Binary download failed — will auto-download on first launch"
fi

# ─── Install Playwright system deps ────────────────────────────────────
info "Installing Playwright system dependencies..."
"$PYTHON" -m playwright install-deps chromium 2>/dev/null || warn "Could not install system deps (may need: sudo playwright install-deps chromium)"

# ─── Run tests ──────────────────────────────────────────────────────────
info "Running tests..."
TEST_OUTPUT=$("$PYTHON" -m pytest tests/ -q --tb=line 2>&1)
echo "$TEST_OUTPUT" | tail -3
if echo "$TEST_OUTPUT" | grep -q "passed"; then
    ok "All tests passed"
else
    warn "Some tests failed — review output above"
fi

# ─── Write wrapper script ──────────────────────────────────────────────
WRAPPER="$INSTALL_DIR/bin/cloakbrowsermcp"
mkdir -p "$INSTALL_DIR/bin"
cat > "$WRAPPER" << 'WRAPPER_EOF'
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$SCRIPT_DIR/.venv/bin/activate"
exec python -m cloakbrowsermcp.server "$@"
WRAPPER_EOF
chmod +x "$WRAPPER"

# ─── Shell PATH hint ───────────────────────────────────────────────────
BIN_DIR="$INSTALL_DIR/bin"
if echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
    ok "cloakbrowsermcp is on your PATH"
else
    # Detect shell config file
    SHELL_RC=""
    case "$SHELL" in
        */zsh)  SHELL_RC="$HOME/.zshrc" ;;
        */bash) SHELL_RC="$HOME/.bashrc" ;;
        */fish) SHELL_RC="$HOME/.config/fish/config.fish" ;;
    esac

    if [ -n "$SHELL_RC" ] && ! grep -q "$BIN_DIR" "$SHELL_RC" 2>/dev/null; then
        echo "" >> "$SHELL_RC"
        echo "# CloakBrowserMCP" >> "$SHELL_RC"
        echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$SHELL_RC"
        ok "Added $BIN_DIR to PATH in $SHELL_RC"
        info "Run: source $SHELL_RC  (or open a new terminal)"
    else
        warn "Add to your PATH: export PATH=\"$BIN_DIR:\$PATH\""
    fi
fi

# ─── Done ───────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}✓ CloakBrowserMCP is ready!${NC}"
echo ""
echo -e "  ${BOLD}Run the server:${NC}"
echo "    cloakbrowsermcp"
echo ""
echo -e "  ${BOLD}Claude Desktop / Claude Code config:${NC}"
echo "    {"
echo "      \"mcpServers\": {"
echo "        \"cloakbrowser\": {"
echo "          \"command\": \"$WRAPPER\""
echo "        }"
echo "      }"
echo "    }"
echo ""
echo -e "  ${BOLD}Run tests:${NC}"
echo "    cd $INSTALL_DIR && source .venv/bin/activate && pytest"
echo ""
