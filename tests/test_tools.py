"""Tests for MCP tool definitions and handlers — the core server tools."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from cloakbrowsermcp.tools import (
    handle_launch_browser,
    handle_close_browser,
    handle_new_page,
    handle_close_page,
    handle_navigate,
    handle_click,
    handle_type_text,
    handle_screenshot,
    handle_get_content,
    handle_evaluate,
    handle_wait_for_selector,
    handle_fill_form,
    handle_hover,
    handle_select_option,
    handle_press_key,
    handle_scroll,
    handle_get_cookies,
    handle_set_cookies,
    handle_get_page_info,
    handle_pdf,
    handle_snapshot,
    handle_click_ref,
    handle_type_ref,
    handle_hover_ref,
    handle_select_ref,
    handle_check_ref,
    handle_get_console,
    handle_smart_action,
    handle_get_text,
    handle_get_links,
    handle_get_form_fields,
)
from cloakbrowsermcp.session import BrowserSession, SessionConfig


def _make_session_with_page():
    """Create a mock session with a browser and page ready."""
    session = MagicMock(spec=BrowserSession)
    session.is_running = True

    mock_page = AsyncMock()
    mock_page.url = "https://example.com"
    mock_page.title = AsyncMock(return_value="Example")
    mock_page.content = AsyncMock(return_value="<html><body>Hello</body></html>")

    session.get_page = MagicMock(return_value=mock_page)
    session.pages = {"page_001": mock_page}
    session.set_refs = MagicMock()
    session.get_refs = MagicMock(return_value={})
    session.get_console_messages = MagicMock(return_value=[])
    session.clear_console_messages = MagicMock()

    return session, mock_page


class TestLaunchBrowser:
    """Test launch_browser tool."""

    @pytest.mark.asyncio
    async def test_launch_default(self):
        session = MagicMock(spec=BrowserSession)
        session.is_running = False
        session.launch = AsyncMock()
        session.new_page = AsyncMock(return_value="page_001")
        session._browser = None
        session._context = None

        result = await handle_launch_browser(session, {})

        session.launch.assert_called_once()
        assert "page_001" in result["page_id"]

    @pytest.mark.asyncio
    async def test_launch_with_proxy(self):
        session = MagicMock(spec=BrowserSession)
        session.is_running = False
        session.launch = AsyncMock()
        session.new_page = AsyncMock(return_value="page_001")
        session._browser = None
        session._context = None

        result = await handle_launch_browser(session, {
            "proxy": "http://user:pass@proxy:8080",
            "humanize": True,
        })

        cfg = session.launch.call_args[0][0]
        assert cfg.proxy == "http://user:pass@proxy:8080"
        assert cfg.humanize is True

    @pytest.mark.asyncio
    async def test_launch_already_running(self):
        session = MagicMock(spec=BrowserSession)
        session.is_running = True

        result = await handle_launch_browser(session, {})

        assert "already running" in result["status"].lower()


class TestCloseBrowser:
    """Test close_browser tool."""

    @pytest.mark.asyncio
    async def test_close(self):
        session = MagicMock(spec=BrowserSession)
        session.is_running = True
        session.close = AsyncMock()

        result = await handle_close_browser(session, {})

        session.close.assert_called_once()
        assert result["status"] == "closed"

    @pytest.mark.asyncio
    async def test_close_not_running(self):
        session = MagicMock(spec=BrowserSession)
        session.is_running = False

        result = await handle_close_browser(session, {})

        assert "not running" in result["status"].lower()


class TestNewPage:
    """Test new_page tool."""

    @pytest.mark.asyncio
    async def test_new_page(self):
        session = MagicMock(spec=BrowserSession)
        session.is_running = True
        session.new_page = AsyncMock(return_value="page_002")

        result = await handle_new_page(session, {})

        assert result["page_id"] == "page_002"

    @pytest.mark.asyncio
    async def test_new_page_with_url(self):
        session, mock_page = _make_session_with_page()
        session.new_page = AsyncMock(return_value="page_002")
        session.get_page = MagicMock(return_value=mock_page)

        result = await handle_new_page(session, {"url": "https://example.com"})

        assert result["page_id"] == "page_002"


class TestClosePage:
    """Test close_page tool."""

    @pytest.mark.asyncio
    async def test_close_page(self):
        session = MagicMock(spec=BrowserSession)
        session.is_running = True
        session.close_page = AsyncMock()

        result = await handle_close_page(session, {"page_id": "page_001"})

        session.close_page.assert_called_once_with("page_001")
        assert result["status"] == "closed"


class TestNavigate:
    """Test navigate tool."""

    @pytest.mark.asyncio
    async def test_navigate(self):
        session, mock_page = _make_session_with_page()
        mock_page.goto = AsyncMock()
        mock_page.url = "https://example.com"
        mock_page.title = AsyncMock(return_value="Example Domain")

        result = await handle_navigate(session, {
            "page_id": "page_001",
            "url": "https://example.com",
        })

        mock_page.goto.assert_called_once_with("https://example.com", wait_until="domcontentloaded", timeout=30000)
        assert result["url"] == "https://example.com"
        assert result["title"] == "Example Domain"

    @pytest.mark.asyncio
    async def test_navigate_with_wait_until(self):
        session, mock_page = _make_session_with_page()
        mock_page.goto = AsyncMock()
        mock_page.title = AsyncMock(return_value="Test")

        await handle_navigate(session, {
            "page_id": "page_001",
            "url": "https://example.com",
            "wait_until": "networkidle",
        })

        mock_page.goto.assert_called_once_with("https://example.com", wait_until="networkidle", timeout=30000)


class TestClick:
    """Test click tool."""

    @pytest.mark.asyncio
    async def test_click_selector(self):
        session, mock_page = _make_session_with_page()
        mock_page.click = AsyncMock()

        result = await handle_click(session, {
            "page_id": "page_001",
            "selector": "button#submit",
        })

        mock_page.click.assert_called_once_with("button#submit", timeout=5000)
        assert result["status"] == "clicked"

    @pytest.mark.asyncio
    async def test_click_with_timeout(self):
        session, mock_page = _make_session_with_page()
        mock_page.click = AsyncMock()

        await handle_click(session, {
            "page_id": "page_001",
            "selector": "a.link",
            "timeout": 10000,
        })

        mock_page.click.assert_called_once_with("a.link", timeout=10000)


class TestTypeText:
    """Test type_text tool."""

    @pytest.mark.asyncio
    async def test_type_text(self):
        session, mock_page = _make_session_with_page()
        mock_page.type = AsyncMock()

        result = await handle_type_text(session, {
            "page_id": "page_001",
            "selector": "input#email",
            "text": "user@example.com",
        })

        mock_page.type.assert_called_once_with("input#email", "user@example.com", delay=0)
        assert result["status"] == "typed"

    @pytest.mark.asyncio
    async def test_type_with_delay(self):
        session, mock_page = _make_session_with_page()
        mock_page.type = AsyncMock()

        await handle_type_text(session, {
            "page_id": "page_001",
            "selector": "input#search",
            "text": "hello",
            "delay": 50,
        })

        mock_page.type.assert_called_once_with("input#search", "hello", delay=50)


class TestScreenshot:
    """Test screenshot tool."""

    @pytest.mark.asyncio
    async def test_screenshot_returns_file_path(self):
        session, mock_page = _make_session_with_page()
        mock_page.screenshot = AsyncMock(return_value=b"\x89PNG\r\n")

        result = await handle_screenshot(session, {"page_id": "page_001"})

        assert "path" in result
        assert result["mime_type"] == "image/png"
        assert result["size_bytes"] > 0

    @pytest.mark.asyncio
    async def test_screenshot_full_page(self):
        session, mock_page = _make_session_with_page()
        mock_page.screenshot = AsyncMock(return_value=b"\x89PNG\r\n")

        await handle_screenshot(session, {
            "page_id": "page_001",
            "full_page": True,
        })

        call_kwargs = mock_page.screenshot.call_args.kwargs
        assert call_kwargs["full_page"] is True

    @pytest.mark.asyncio
    async def test_screenshot_selector(self):
        session, mock_page = _make_session_with_page()
        mock_locator = AsyncMock()
        mock_locator.screenshot = AsyncMock(return_value=b"\x89PNG\r\n")
        mock_page.locator = MagicMock(return_value=mock_locator)

        result = await handle_screenshot(session, {
            "page_id": "page_001",
            "selector": "#main-content",
        })

        mock_page.locator.assert_called_once_with("#main-content")
        assert "path" in result


class TestGetContent:
    """Test get_content tool."""

    @pytest.mark.asyncio
    async def test_get_html(self):
        session, mock_page = _make_session_with_page()

        result = await handle_get_content(session, {"page_id": "page_001"})

        assert result["content"] == "<html><body>Hello</body></html>"

    @pytest.mark.asyncio
    async def test_get_text(self):
        session, mock_page = _make_session_with_page()
        mock_page.inner_text = AsyncMock(return_value="Hello World")

        result = await handle_get_content(session, {
            "page_id": "page_001",
            "selector": "body",
            "content_type": "text",
        })

        assert result["content"] == "Hello World"

    @pytest.mark.asyncio
    async def test_get_outer_html(self):
        session, mock_page = _make_session_with_page()
        mock_locator = AsyncMock()
        mock_locator.evaluate = AsyncMock(return_value="<div>content</div>")
        mock_page.locator = MagicMock(return_value=mock_locator)

        result = await handle_get_content(session, {
            "page_id": "page_001",
            "selector": "div.main",
            "content_type": "outer_html",
        })

        assert result["content"] == "<div>content</div>"


class TestEvaluate:
    """Test evaluate tool."""

    @pytest.mark.asyncio
    async def test_evaluate_expression(self):
        session, mock_page = _make_session_with_page()
        mock_page.evaluate = AsyncMock(return_value=42)

        result = await handle_evaluate(session, {
            "page_id": "page_001",
            "expression": "2 + 40",
        })

        assert result["result"] == 42

    @pytest.mark.asyncio
    async def test_evaluate_returns_json_serializable(self):
        session, mock_page = _make_session_with_page()
        mock_page.evaluate = AsyncMock(return_value={"key": "value"})

        result = await handle_evaluate(session, {
            "page_id": "page_001",
            "expression": "({key: 'value'})",
        })

        assert result["result"] == {"key": "value"}


class TestWaitForSelector:
    """Test wait_for_selector tool."""

    @pytest.mark.asyncio
    async def test_wait_for_selector(self):
        session, mock_page = _make_session_with_page()
        mock_page.wait_for_selector = AsyncMock()

        result = await handle_wait_for_selector(session, {
            "page_id": "page_001",
            "selector": "#loaded",
        })

        mock_page.wait_for_selector.assert_called_once_with("#loaded", state="visible", timeout=30000)
        assert result["status"] == "found"

    @pytest.mark.asyncio
    async def test_wait_for_hidden(self):
        session, mock_page = _make_session_with_page()
        mock_page.wait_for_selector = AsyncMock()

        await handle_wait_for_selector(session, {
            "page_id": "page_001",
            "selector": "#spinner",
            "state": "hidden",
        })

        mock_page.wait_for_selector.assert_called_once_with("#spinner", state="hidden", timeout=30000)


class TestFillForm:
    """Test fill_form tool."""

    @pytest.mark.asyncio
    async def test_fill_form(self):
        session, mock_page = _make_session_with_page()
        mock_page.fill = AsyncMock()

        result = await handle_fill_form(session, {
            "page_id": "page_001",
            "selector": "input#name",
            "value": "John Doe",
        })

        mock_page.fill.assert_called_once_with("input#name", "John Doe")
        assert result["status"] == "filled"


class TestHover:
    """Test hover tool."""

    @pytest.mark.asyncio
    async def test_hover(self):
        session, mock_page = _make_session_with_page()
        mock_page.hover = AsyncMock()

        result = await handle_hover(session, {
            "page_id": "page_001",
            "selector": "button.menu",
        })

        mock_page.hover.assert_called_once_with("button.menu")
        assert result["status"] == "hovered"


class TestSelectOption:
    """Test select_option tool."""

    @pytest.mark.asyncio
    async def test_select_by_value(self):
        session, mock_page = _make_session_with_page()
        mock_page.select_option = AsyncMock(return_value=["us"])

        result = await handle_select_option(session, {
            "page_id": "page_001",
            "selector": "select#country",
            "value": "us",
        })

        mock_page.select_option.assert_called_once_with("select#country", value="us")
        assert result["selected"] == ["us"]


class TestPressKey:
    """Test press_key tool."""

    @pytest.mark.asyncio
    async def test_press_enter(self):
        session, mock_page = _make_session_with_page()
        mock_page.keyboard = MagicMock()
        mock_page.keyboard.press = AsyncMock()

        result = await handle_press_key(session, {
            "page_id": "page_001",
            "key": "Enter",
        })

        mock_page.keyboard.press.assert_called_once_with("Enter")
        assert result["status"] == "pressed"


class TestScroll:
    """Test scroll tool."""

    @pytest.mark.asyncio
    async def test_scroll_down(self):
        session, mock_page = _make_session_with_page()
        mock_page.evaluate = AsyncMock(return_value=None)

        result = await handle_scroll(session, {
            "page_id": "page_001",
            "direction": "down",
            "amount": 500,
        })

        assert result["status"] == "scrolled"


class TestGetCookies:
    """Test get_cookies tool."""

    @pytest.mark.asyncio
    async def test_get_cookies(self):
        session, mock_page = _make_session_with_page()
        mock_context = MagicMock()
        mock_context.cookies = AsyncMock(return_value=[
            {"name": "session", "value": "abc123", "domain": "example.com"}
        ])
        mock_page.context = mock_context

        result = await handle_get_cookies(session, {"page_id": "page_001"})

        assert len(result["cookies"]) == 1
        assert result["cookies"][0]["name"] == "session"


class TestSetCookies:
    """Test set_cookies tool."""

    @pytest.mark.asyncio
    async def test_set_cookies(self):
        session, mock_page = _make_session_with_page()
        mock_context = MagicMock()
        mock_context.add_cookies = AsyncMock()
        mock_page.context = mock_context

        cookies = [{"name": "token", "value": "xyz", "domain": "example.com", "path": "/"}]

        result = await handle_set_cookies(session, {
            "page_id": "page_001",
            "cookies": cookies,
        })

        mock_context.add_cookies.assert_called_once_with(cookies)
        assert result["status"] == "set"


class TestGetPageInfo:
    """Test get_page_info tool."""

    @pytest.mark.asyncio
    async def test_get_page_info(self):
        session, mock_page = _make_session_with_page()

        result = await handle_get_page_info(session, {"page_id": "page_001"})

        assert result["url"] == "https://example.com"
        assert result["title"] == "Example"


class TestPdf:
    """Test pdf tool."""

    @pytest.mark.asyncio
    async def test_pdf(self):
        session, mock_page = _make_session_with_page()
        mock_page.pdf = AsyncMock(return_value=b"%PDF-1.4")

        result = await handle_pdf(session, {"page_id": "page_001"})

        assert "path" in result
        assert result["mime_type"] == "application/pdf"
        assert result["size_bytes"] > 0


# ---------------------------------------------------------------------------
# New tools: snapshot, click_ref, type_ref, get_console
# ---------------------------------------------------------------------------

class TestSnapshot:
    """Test snapshot tool — accessibility tree with ref IDs."""

    @pytest.mark.asyncio
    async def test_snapshot_returns_text(self):
        session, mock_page = _make_session_with_page()
        mock_page.evaluate = AsyncMock(return_value={
            "snapshot": 'Page: Example\nURL: https://example.com\n---\n[@e1] button "Submit"',
            "ref_count": 1,
            "refs": {"e1": {"selector": "button#submit", "tag": "button"}},
        })

        result = await handle_snapshot(session, {"page_id": "page_001"})

        assert "snapshot" in result
        assert "[@e1]" in result["snapshot"]
        assert result["interactive_elements"] == 1
        session.set_refs.assert_called_once()

    @pytest.mark.asyncio
    async def test_snapshot_truncation(self):
        session, mock_page = _make_session_with_page()
        long_snapshot = "x" * 10000
        mock_page.evaluate = AsyncMock(return_value={
            "snapshot": long_snapshot,
            "ref_count": 100,
            "refs": {},
        })

        result = await handle_snapshot(session, {
            "page_id": "page_001",
            "max_length": 500,
        })

        assert result["truncated"] is True
        assert len(result["snapshot"]) < len(long_snapshot)


class TestClickRef:
    """Test click_ref tool — click by ref ID from snapshot."""

    @pytest.mark.asyncio
    async def test_click_ref_success(self):
        session, mock_page = _make_session_with_page()
        mock_page.click = AsyncMock()
        session.get_refs = MagicMock(return_value={
            "e1": {"selector": "button#submit", "tag": "button"}
        })

        result = await handle_click_ref(session, {
            "page_id": "page_001",
            "ref": "@e1",
        })

        mock_page.click.assert_called_once_with("button#submit", timeout=5000)
        assert result["status"] == "clicked"

    @pytest.mark.asyncio
    async def test_click_ref_not_found(self):
        session, mock_page = _make_session_with_page()
        session.get_refs = MagicMock(return_value={})

        with pytest.raises(KeyError, match="not found"):
            await handle_click_ref(session, {
                "page_id": "page_001",
                "ref": "@e99",
            })

    @pytest.mark.asyncio
    async def test_click_ref_without_at_prefix(self):
        session, mock_page = _make_session_with_page()
        mock_page.click = AsyncMock()
        session.get_refs = MagicMock(return_value={
            "e5": {"selector": "a.link", "tag": "a"}
        })

        result = await handle_click_ref(session, {
            "page_id": "page_001",
            "ref": "e5",
        })

        assert result["status"] == "clicked"


class TestTypeRef:
    """Test type_ref tool — type into input by ref ID."""

    @pytest.mark.asyncio
    async def test_type_ref_success(self):
        session, mock_page = _make_session_with_page()
        mock_page.fill = AsyncMock()
        mock_page.type = AsyncMock()
        session.get_refs = MagicMock(return_value={
            "e3": {"selector": "input#email", "tag": "input"}
        })

        result = await handle_type_ref(session, {
            "page_id": "page_001",
            "ref": "@e3",
            "text": "user@example.com",
        })

        assert result["status"] == "typed"
        # Should clear first by default
        mock_page.fill.assert_called_once_with("input#email", "")
        mock_page.type.assert_called_once()

    @pytest.mark.asyncio
    async def test_type_ref_no_clear(self):
        session, mock_page = _make_session_with_page()
        mock_page.fill = AsyncMock()
        mock_page.type = AsyncMock()
        session.get_refs = MagicMock(return_value={
            "e3": {"selector": "input#email", "tag": "input"}
        })

        result = await handle_type_ref(session, {
            "page_id": "page_001",
            "ref": "@e3",
            "text": "append this",
            "clear": False,
        })

        assert result["status"] == "typed"
        mock_page.fill.assert_not_called()

    @pytest.mark.asyncio
    async def test_type_ref_not_found(self):
        session, mock_page = _make_session_with_page()
        session.get_refs = MagicMock(return_value={})

        with pytest.raises(KeyError, match="not found"):
            await handle_type_ref(session, {
                "page_id": "page_001",
                "ref": "@e99",
                "text": "hello",
            })

    @pytest.mark.asyncio
    async def test_type_ref_with_submit(self):
        session, mock_page = _make_session_with_page()
        mock_page.fill = AsyncMock()
        mock_page.type = AsyncMock()
        mock_page.press = AsyncMock()
        session.get_refs = MagicMock(return_value={
            "e3": {"selector": "input#search", "tag": "input"}
        })

        result = await handle_type_ref(session, {
            "page_id": "page_001",
            "ref": "@e3",
            "text": "search query",
            "submit": True,
        })

        assert result["status"] == "typed"
        assert result["submitted"] is True
        mock_page.press.assert_called_once_with("input#search", "Enter")


class TestGetConsole:
    """Test get_console tool."""

    @pytest.mark.asyncio
    async def test_get_console_messages(self):
        session, mock_page = _make_session_with_page()
        session.get_console_messages = MagicMock(return_value=[
            {"type": "log", "text": "Hello from console"},
            {"type": "error", "text": "Something failed"},
        ])

        result = await handle_get_console(session, {"page_id": "page_001"})

        assert result["total"] == 2
        assert len(result["messages"]) == 2

    @pytest.mark.asyncio
    async def test_get_console_with_clear(self):
        session, mock_page = _make_session_with_page()
        session.get_console_messages = MagicMock(return_value=[])

        result = await handle_get_console(session, {
            "page_id": "page_001",
            "clear": True,
        })

        session.clear_console_messages.assert_called_once_with("page_001")


class TestGetText:
    """Test get_text tool."""

    @pytest.mark.asyncio
    async def test_get_text_basic(self):
        session, mock_page = _make_session_with_page()
        mock_page.inner_text = AsyncMock(return_value="Hello World\n\n\n\nExtra space")

        result = await handle_get_text(session, {"page_id": "page_001"})

        assert "Hello World" in result["text"]
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_get_text_truncation(self):
        session, mock_page = _make_session_with_page()
        mock_page.inner_text = AsyncMock(return_value="x" * 100000)

        result = await handle_get_text(session, {
            "page_id": "page_001",
            "max_length": 1000,
        })

        assert result["truncated"] is True


class TestSmartAction:
    """Test smart_action tool."""

    @pytest.mark.asyncio
    async def test_smart_action_click(self):
        session, mock_page = _make_session_with_page()

        mock_locator = AsyncMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_locator.first = AsyncMock()
        mock_locator.first.click = AsyncMock()

        mock_page.get_by_text = MagicMock(return_value=mock_locator)

        result = await handle_smart_action(session, {
            "page_id": "page_001",
            "text": "Submit",
        })

        assert result["status"] == "clicked"

    @pytest.mark.asyncio
    async def test_smart_action_not_found(self):
        session, mock_page = _make_session_with_page()

        # All strategies fail
        mock_locator = AsyncMock()
        mock_locator.count = AsyncMock(return_value=0)
        mock_page.get_by_text = MagicMock(return_value=mock_locator)
        mock_page.get_by_role = MagicMock(return_value=mock_locator)
        mock_page.get_by_label = MagicMock(return_value=mock_locator)
        mock_page.get_by_placeholder = MagicMock(return_value=mock_locator)
        mock_page.get_by_title = MagicMock(return_value=mock_locator)
        mock_page.get_by_alt_text = MagicMock(return_value=mock_locator)
        mock_page.click = AsyncMock(side_effect=Exception("not found"))

        result = await handle_smart_action(session, {
            "page_id": "page_001",
            "text": "Nonexistent Button",
        })

        assert result["status"] == "not_found"
        assert "hint" in result


# ---------------------------------------------------------------------------
# New ref-based tools: hover_ref, select_ref, check_ref
# ---------------------------------------------------------------------------

class TestHoverRef:
    """Test hover_ref tool — hover by ref ID from snapshot."""

    @pytest.mark.asyncio
    async def test_hover_ref_success(self):
        session, mock_page = _make_session_with_page()
        mock_page.hover = AsyncMock()
        session.get_refs = MagicMock(return_value={
            "e7": {"selector": "nav.menu", "tag": "nav"}
        })

        result = await handle_hover_ref(session, {
            "page_id": "page_001",
            "ref": "@e7",
        })

        mock_page.hover.assert_called_once_with("nav.menu")
        assert result["status"] == "hovered"
        assert result["ref"] == "@e7"

    @pytest.mark.asyncio
    async def test_hover_ref_not_found(self):
        session, mock_page = _make_session_with_page()
        session.get_refs = MagicMock(return_value={})

        with pytest.raises(KeyError, match="not found"):
            await handle_hover_ref(session, {
                "page_id": "page_001",
                "ref": "@e99",
            })


class TestSelectRef:
    """Test select_ref tool — select dropdown option by ref ID."""

    @pytest.mark.asyncio
    async def test_select_ref_by_label(self):
        session, mock_page = _make_session_with_page()
        mock_page.select_option = AsyncMock(return_value=["us"])
        session.get_refs = MagicMock(return_value={
            "e4": {"selector": "select#country", "tag": "select"}
        })

        result = await handle_select_ref(session, {
            "page_id": "page_001",
            "ref": "@e4",
            "label": "United States",
        })

        mock_page.select_option.assert_called_once_with("select#country", label="United States")
        assert result["status"] == "selected"

    @pytest.mark.asyncio
    async def test_select_ref_by_value(self):
        session, mock_page = _make_session_with_page()
        mock_page.select_option = AsyncMock(return_value=["us"])
        session.get_refs = MagicMock(return_value={
            "e4": {"selector": "select#country", "tag": "select"}
        })

        result = await handle_select_ref(session, {
            "page_id": "page_001",
            "ref": "@e4",
            "value": "us",
        })

        mock_page.select_option.assert_called_once_with("select#country", value="us")
        assert result["status"] == "selected"

    @pytest.mark.asyncio
    async def test_select_ref_no_option_provided(self):
        session, mock_page = _make_session_with_page()
        session.get_refs = MagicMock(return_value={
            "e4": {"selector": "select#country", "tag": "select"}
        })

        result = await handle_select_ref(session, {
            "page_id": "page_001",
            "ref": "@e4",
        })

        assert "error" in result


class TestCheckRef:
    """Test check_ref tool — check/uncheck checkbox by ref ID."""

    @pytest.mark.asyncio
    async def test_check_ref(self):
        session, mock_page = _make_session_with_page()
        mock_page.check = AsyncMock()
        session.get_refs = MagicMock(return_value={
            "e8": {"selector": "input#agree", "tag": "input"}
        })

        result = await handle_check_ref(session, {
            "page_id": "page_001",
            "ref": "@e8",
        })

        mock_page.check.assert_called_once_with("input#agree")
        assert result["status"] == "checked"

    @pytest.mark.asyncio
    async def test_uncheck_ref(self):
        session, mock_page = _make_session_with_page()
        mock_page.uncheck = AsyncMock()
        session.get_refs = MagicMock(return_value={
            "e8": {"selector": "input#agree", "tag": "input"}
        })

        result = await handle_check_ref(session, {
            "page_id": "page_001",
            "ref": "@e8",
            "checked": False,
        })

        mock_page.uncheck.assert_called_once_with("input#agree")
        assert result["status"] == "unchecked"

    @pytest.mark.asyncio
    async def test_check_ref_not_found(self):
        session, mock_page = _make_session_with_page()
        session.get_refs = MagicMock(return_value={})

        with pytest.raises(KeyError, match="not found"):
            await handle_check_ref(session, {
                "page_id": "page_001",
                "ref": "@e99",
            })
