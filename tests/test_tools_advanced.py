"""Tests for advanced tools — stealth configuration, network interception, navigation helpers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from cloakbrowsermcp.tools_advanced import (
    handle_stealth_config,
    handle_get_binary_info,
    handle_network_intercept,
    handle_network_continue,
    handle_wait_for_navigation,
    handle_go_back,
    handle_go_forward,
    handle_reload,
    handle_set_viewport,
    handle_emulate_media,
    handle_add_init_script,
)
from cloakbrowsermcp.session import BrowserSession


def _make_session_with_page():
    """Create a mock session with a browser and page ready."""
    session = MagicMock(spec=BrowserSession)
    session.is_running = True

    mock_page = AsyncMock()
    mock_page.url = "https://example.com"
    mock_page.title = AsyncMock(return_value="Example")

    session.get_page = MagicMock(return_value=mock_page)
    session.pages = {"page_001": mock_page}

    return session, mock_page


class TestStealthConfig:
    """Test stealth configuration inspection."""

    @pytest.mark.asyncio
    async def test_get_stealth_config(self):
        with patch("cloakbrowsermcp.tools_advanced.get_default_stealth_args") as mock_args:
            mock_args.return_value = [
                "--no-sandbox",
                "--fingerprint=12345",
                "--fingerprint-platform=windows",
            ]

            result = await handle_stealth_config({})

            assert "args" in result
            assert "--fingerprint=12345" in result["args"]


class TestGetBinaryInfo:
    """Test binary info retrieval."""

    @pytest.mark.asyncio
    async def test_get_binary_info(self):
        with patch("cloakbrowsermcp.tools_advanced.binary_info") as mock_info:
            mock_info.return_value = {
                "version": "145.0.7632.159.7",
                "platform": "darwin-arm64",
                "installed": True,
            }

            result = await handle_get_binary_info({})

            assert result["version"] == "145.0.7632.159.7"
            assert result["installed"] is True


class TestNetworkIntercept:
    """Test network interception."""

    @pytest.mark.asyncio
    async def test_intercept_route(self):
        session, mock_page = _make_session_with_page()
        mock_page.route = AsyncMock()

        result = await handle_network_intercept(session, {
            "page_id": "page_001",
            "url_pattern": "**/api/**",
            "action": "block",
        })

        assert result["status"] == "intercepting"

    @pytest.mark.asyncio
    async def test_intercept_modify(self):
        session, mock_page = _make_session_with_page()
        mock_page.route = AsyncMock()

        result = await handle_network_intercept(session, {
            "page_id": "page_001",
            "url_pattern": "**/analytics/**",
            "action": "block",
        })

        assert result["status"] == "intercepting"


class TestNetworkContinue:
    """Test removing network interception."""

    @pytest.mark.asyncio
    async def test_unroute(self):
        session, mock_page = _make_session_with_page()
        mock_page.unroute = AsyncMock()

        result = await handle_network_continue(session, {
            "page_id": "page_001",
            "url_pattern": "**/api/**",
        })

        assert result["status"] == "unrouted"


class TestNavigation:
    """Test navigation helpers."""

    @pytest.mark.asyncio
    async def test_wait_for_navigation(self):
        session, mock_page = _make_session_with_page()
        mock_page.wait_for_load_state = AsyncMock()

        result = await handle_wait_for_navigation(session, {
            "page_id": "page_001",
        })

        assert result["status"] == "loaded"

    @pytest.mark.asyncio
    async def test_go_back(self):
        session, mock_page = _make_session_with_page()
        mock_page.go_back = AsyncMock()
        mock_page.url = "https://example.com/prev"
        mock_page.title = AsyncMock(return_value="Previous Page")

        result = await handle_go_back(session, {"page_id": "page_001"})

        mock_page.go_back.assert_called_once()
        assert result["url"] == "https://example.com/prev"

    @pytest.mark.asyncio
    async def test_go_forward(self):
        session, mock_page = _make_session_with_page()
        mock_page.go_forward = AsyncMock()
        mock_page.url = "https://example.com/next"
        mock_page.title = AsyncMock(return_value="Next Page")

        result = await handle_go_forward(session, {"page_id": "page_001"})

        mock_page.go_forward.assert_called_once()
        assert result["url"] == "https://example.com/next"

    @pytest.mark.asyncio
    async def test_reload(self):
        session, mock_page = _make_session_with_page()
        mock_page.reload = AsyncMock()
        mock_page.title = AsyncMock(return_value="Reloaded")

        result = await handle_reload(session, {"page_id": "page_001"})

        mock_page.reload.assert_called_once()


class TestViewport:
    """Test viewport manipulation."""

    @pytest.mark.asyncio
    async def test_set_viewport(self):
        session, mock_page = _make_session_with_page()
        mock_page.set_viewport_size = AsyncMock()

        result = await handle_set_viewport(session, {
            "page_id": "page_001",
            "width": 1280,
            "height": 720,
        })

        mock_page.set_viewport_size.assert_called_once_with({"width": 1280, "height": 720})
        assert result["status"] == "viewport_set"


class TestEmulateMedia:
    """Test media emulation."""

    @pytest.mark.asyncio
    async def test_emulate_dark_mode(self):
        session, mock_page = _make_session_with_page()
        mock_page.emulate_media = AsyncMock()

        result = await handle_emulate_media(session, {
            "page_id": "page_001",
            "color_scheme": "dark",
        })

        mock_page.emulate_media.assert_called_once()
        assert result["status"] == "emulated"


class TestInitScript:
    """Test page init script injection."""

    @pytest.mark.asyncio
    async def test_add_init_script(self):
        session, mock_page = _make_session_with_page()
        mock_page.add_init_script = AsyncMock()

        result = await handle_add_init_script(session, {
            "page_id": "page_001",
            "script": "window.__test = true;",
        })

        mock_page.add_init_script.assert_called_once_with("window.__test = true;")
        assert result["status"] == "added"
