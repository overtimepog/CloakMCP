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

    return session, mock_page


class TestLaunchBrowser:
    """Test launch_browser tool."""

    @pytest.mark.asyncio
    async def test_launch_default(self):
        session = MagicMock(spec=BrowserSession)
        session.is_running = False
        session.launch = AsyncMock()
        session.new_page = AsyncMock(return_value="page_001")

        result = await handle_launch_browser(session, {})

        session.launch.assert_called_once()
        assert "page_001" in result["page_id"]

    @pytest.mark.asyncio
    async def test_launch_with_proxy(self):
        session = MagicMock(spec=BrowserSession)
        session.is_running = False
        session.launch = AsyncMock()
        session.new_page = AsyncMock(return_value="page_001")

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
    async def test_screenshot_returns_base64(self):
        session, mock_page = _make_session_with_page()
        mock_page.screenshot = AsyncMock(return_value=b"\x89PNG\r\n")

        result = await handle_screenshot(session, {"page_id": "page_001"})

        assert "data" in result
        assert result["mime_type"] == "image/png"

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
        assert "data" in result


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

        assert "data" in result
        assert result["mime_type"] == "application/pdf"
