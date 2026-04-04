"""Tests for error handling and edge cases across the tool handlers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from cloakbrowsermcp.tools import (
    handle_navigate,
    handle_click,
    handle_type_text,
    handle_screenshot,
    handle_evaluate,
    handle_wait_for_selector,
    handle_scroll,
    handle_snapshot,
    handle_click_ref,
    handle_type_ref,
)
from cloakbrowsermcp.session import BrowserSession, PageNotFoundError, BrowserSessionError


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

    return session, mock_page


class TestNavigateErrors:
    """Test error handling in navigate."""

    @pytest.mark.asyncio
    async def test_navigate_page_not_found(self):
        session = MagicMock(spec=BrowserSession)
        session.get_page = MagicMock(side_effect=PageNotFoundError("no_page"))

        with pytest.raises(PageNotFoundError):
            await handle_navigate(session, {
                "page_id": "no_page",
                "url": "https://example.com",
            })

    @pytest.mark.asyncio
    async def test_navigate_timeout(self):
        session, mock_page = _make_session_with_page()
        mock_page.goto = AsyncMock(side_effect=PlaywrightTimeoutError("Timeout"))

        with pytest.raises(PlaywrightTimeoutError):
            await handle_navigate(session, {
                "page_id": "page_001",
                "url": "https://slow-site.com",
                "timeout": 1000,
            })


class TestClickErrors:
    """Test error handling in click."""

    @pytest.mark.asyncio
    async def test_click_element_not_found(self):
        session, mock_page = _make_session_with_page()
        mock_page.click = AsyncMock(side_effect=PlaywrightTimeoutError("Element not found"))

        with pytest.raises(PlaywrightTimeoutError):
            await handle_click(session, {
                "page_id": "page_001",
                "selector": "#nonexistent",
            })


class TestTypeErrors:
    """Test error handling in type_text."""

    @pytest.mark.asyncio
    async def test_type_empty_text(self):
        session, mock_page = _make_session_with_page()
        mock_page.type = AsyncMock()

        result = await handle_type_text(session, {
            "page_id": "page_001",
            "selector": "input",
            "text": "",
        })

        assert result["status"] == "typed"
        assert result["length"] == 0


class TestScreenshotEdge:
    """Test screenshot edge cases."""

    @pytest.mark.asyncio
    async def test_screenshot_default_no_fullpage(self):
        session, mock_page = _make_session_with_page()
        mock_page.screenshot = AsyncMock(return_value=b"\x89PNG")

        result = await handle_screenshot(session, {"page_id": "page_001"})

        call_kwargs = mock_page.screenshot.call_args.kwargs
        assert call_kwargs.get("full_page", False) is False
        # Should return file path, not base64
        assert "path" in result


class TestEvaluateEdge:
    """Test evaluate edge cases."""

    @pytest.mark.asyncio
    async def test_evaluate_returns_none(self):
        session, mock_page = _make_session_with_page()
        mock_page.evaluate = AsyncMock(return_value=None)

        result = await handle_evaluate(session, {
            "page_id": "page_001",
            "expression": "undefined",
        })

        assert result["result"] is None

    @pytest.mark.asyncio
    async def test_evaluate_returns_list(self):
        session, mock_page = _make_session_with_page()
        mock_page.evaluate = AsyncMock(return_value=[1, 2, 3])

        result = await handle_evaluate(session, {
            "page_id": "page_001",
            "expression": "[1, 2, 3]",
        })

        assert result["result"] == [1, 2, 3]


class TestScrollEdge:
    """Test scroll edge cases."""

    @pytest.mark.asyncio
    async def test_scroll_up(self):
        session, mock_page = _make_session_with_page()
        mock_page.evaluate = AsyncMock()

        result = await handle_scroll(session, {
            "page_id": "page_001",
            "direction": "up",
            "amount": 200,
        })

        assert result["direction"] == "up"
        # Verify negative scroll value was passed
        call_args = mock_page.evaluate.call_args[0][0]
        assert "-200" in call_args


class TestNavigateStatus:
    """Test navigate returns status field."""

    @pytest.mark.asyncio
    async def test_navigate_returns_status(self):
        session, mock_page = _make_session_with_page()
        mock_page.goto = AsyncMock()
        mock_page.url = "https://example.com"
        mock_page.title = AsyncMock(return_value="Example")

        result = await handle_navigate(session, {
            "page_id": "page_001",
            "url": "https://example.com",
        })

        assert result["status"] == "navigated"
        assert result["url"] == "https://example.com"
        assert result["title"] == "Example"


class TestServerErrorHandling:
    """Test that _safe_call wraps errors into clean JSON responses."""

    @pytest.mark.asyncio
    async def test_safe_call_key_error(self):
        from cloakbrowsermcp.server import _safe_call
        async def bad_handler(session, params):
            raise KeyError("page_xyz")

        result = await _safe_call(bad_handler, None, {})
        assert "error" in result
        assert "page_xyz" in result["error"]

    @pytest.mark.asyncio
    async def test_safe_call_browser_session_error(self):
        from cloakbrowsermcp.server import _safe_call
        async def bad_handler(session, params):
            raise BrowserSessionError("Browser process has died or been disconnected.")

        result = await _safe_call(bad_handler, None, {})
        assert "error" in result
        assert "died" in result["error"]

    @pytest.mark.asyncio
    async def test_safe_call_closed_browser_error(self):
        """Test that _safe_call detects browser-closed errors and cleans up."""
        from cloakbrowsermcp.server import _safe_call
        session = MagicMock(spec=BrowserSession)
        session._force_cleanup = MagicMock()

        async def bad_handler(sess, params):
            raise Exception("Target page, context or browser has been closed")

        result = await _safe_call(bad_handler, session, {})
        assert "error" in result
        assert "Browser session lost" in result["error"]
        session._force_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_safe_call_runtime_error(self):
        from cloakbrowsermcp.server import _safe_call
        async def bad_handler(session, params):
            raise RuntimeError("Browser is not running. Call launch() first.")

        result = await _safe_call(bad_handler, None, {})
        assert "error" in result
        assert "Browser is not running" in result["error"]

    @pytest.mark.asyncio
    async def test_safe_call_generic_exception(self):
        from cloakbrowsermcp.server import _safe_call
        async def bad_handler(session, params):
            raise ValueError("unexpected value")

        result = await _safe_call(bad_handler, None, {})
        assert "error" in result
        assert "ValueError" in result["error"]

    @pytest.mark.asyncio
    async def test_safe_call_success(self):
        from cloakbrowsermcp.server import _safe_call
        async def good_handler(session, params):
            return {"status": "ok", "data": 42}

        result = await _safe_call(good_handler, None, {})
        assert result["status"] == "ok"
        assert result["data"] == 42


class TestSnapshotEdgeCases:
    """Test snapshot edge cases."""

    @pytest.mark.asyncio
    async def test_click_ref_handles_failed_click(self):
        session, mock_page = _make_session_with_page()
        mock_page.click = AsyncMock(side_effect=PlaywrightTimeoutError("Element gone"))
        session.get_refs = MagicMock(return_value={
            "e1": {"selector": "button.gone", "tag": "button"}
        })

        result = await handle_click_ref(session, {
            "page_id": "page_001",
            "ref": "@e1",
        })

        assert "error" in result

    @pytest.mark.asyncio
    async def test_type_ref_handles_failed_type(self):
        session, mock_page = _make_session_with_page()
        mock_page.fill = AsyncMock(side_effect=PlaywrightTimeoutError("Element gone"))
        session.get_refs = MagicMock(return_value={
            "e1": {"selector": "input.gone", "tag": "input"}
        })

        result = await handle_type_ref(session, {
            "page_id": "page_001",
            "ref": "@e1",
            "text": "hello",
        })

        assert "error" in result


class TestSessionMultiPage:
    """Test multi-page management."""

    @pytest.mark.asyncio
    async def test_multiple_pages(self):
        from cloakbrowsermcp.session import BrowserSession, SessionConfig

        session = BrowserSession()
        cfg = SessionConfig()

        with patch("cloakbrowsermcp.session.launch_async") as mock_launch:
            mock_browser = AsyncMock()
            mock_browser.is_connected = MagicMock(return_value=True)

            pages_created = []
            async def make_page():
                mock_page = AsyncMock()
                mock_page.url = "about:blank"
                mock_page.title = AsyncMock(return_value="")
                mock_page.on = MagicMock()
                mock_page.is_closed = MagicMock(return_value=False)
                pages_created.append(mock_page)
                return mock_page

            mock_context = AsyncMock()
            mock_context.new_page = make_page
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_launch.return_value = mock_browser

            await session.launch(cfg)

            id1 = await session.new_page()
            id2 = await session.new_page()
            id3 = await session.new_page()

            assert len(session.pages) == 3
            assert id1 != id2 != id3

            page_list = session.list_pages()
            assert len(page_list) == 3

    @pytest.mark.asyncio
    async def test_close_all_pages_on_browser_close(self):
        from cloakbrowsermcp.session import BrowserSession, SessionConfig

        session = BrowserSession()
        cfg = SessionConfig()

        with patch("cloakbrowsermcp.session.launch_async") as mock_launch:
            mock_browser = AsyncMock()
            mock_browser.is_connected = MagicMock(return_value=True)

            async def make_page():
                mock_page = AsyncMock()
                mock_page.url = "about:blank"
                mock_page.title = AsyncMock(return_value="")
                mock_page.on = MagicMock()
                mock_page.is_closed = MagicMock(return_value=False)
                return mock_page

            mock_context = AsyncMock()
            mock_context.new_page = make_page
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_launch.return_value = mock_browser

            await session.launch(cfg)
            await session.new_page()
            await session.new_page()

            assert len(session.pages) == 2

            await session.close()

            assert len(session.pages) == 0
            assert session.is_running is False
