"""Tests for BrowserSession — the core browser lifecycle manager."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from cloakbrowsermcp.session import BrowserSession, SessionConfig


class TestSessionConfig:
    """Test SessionConfig defaults and construction."""

    def test_default_config(self):
        cfg = SessionConfig()
        assert cfg.headless is True
        assert cfg.proxy is None
        assert cfg.humanize is False
        assert cfg.human_preset == "default"
        assert cfg.stealth_args is True
        assert cfg.timezone is None
        assert cfg.locale is None
        assert cfg.geoip is False
        assert cfg.viewport == {"width": 1920, "height": 947}
        assert cfg.extra_args == []

    def test_custom_config(self):
        cfg = SessionConfig(
            headless=False,
            proxy="http://user:pass@proxy:8080",
            humanize=True,
            human_preset="careful",
            timezone="America/New_York",
            locale="en-US",
            viewport={"width": 1280, "height": 720},
            extra_args=["--fingerprint=42069"],
        )
        assert cfg.headless is False
        assert cfg.proxy == "http://user:pass@proxy:8080"
        assert cfg.humanize is True
        assert cfg.human_preset == "careful"
        assert cfg.timezone == "America/New_York"
        assert cfg.locale == "en-US"
        assert cfg.viewport == {"width": 1280, "height": 720}
        assert cfg.extra_args == ["--fingerprint=42069"]

    def test_fingerprint_seed_config(self):
        cfg = SessionConfig(fingerprint_seed="42069")
        assert cfg.fingerprint_seed == "42069"

    def test_persistent_profile_config(self):
        cfg = SessionConfig(user_data_dir="/tmp/profile")
        assert cfg.user_data_dir == "/tmp/profile"


def _make_mock_page():
    """Create a mock page that supports event handlers."""
    mock_page = AsyncMock()
    mock_page.url = "about:blank"
    mock_page.title = AsyncMock(return_value="")
    mock_page.on = MagicMock()  # Accept event handler registration
    return mock_page


class TestBrowserSession:
    """Test BrowserSession lifecycle."""

    def test_initial_state(self):
        session = BrowserSession()
        assert session.is_running is False
        assert session.pages == {}
        assert session.config is None

    @pytest.mark.asyncio
    async def test_launch_creates_browser(self):
        session = BrowserSession()
        cfg = SessionConfig()

        with patch("cloakbrowsermcp.session.launch_async") as mock_launch:
            mock_browser = AsyncMock()
            mock_launch.return_value = mock_browser

            await session.launch(cfg)

            assert session.is_running is True
            assert session.config is cfg
            mock_launch.assert_called_once()

    @pytest.mark.asyncio
    async def test_launch_with_proxy(self):
        session = BrowserSession()
        cfg = SessionConfig(proxy="http://user:pass@proxy:8080")

        with patch("cloakbrowsermcp.session.launch_async") as mock_launch:
            mock_browser = AsyncMock()
            mock_launch.return_value = mock_browser

            await session.launch(cfg)

            call_kwargs = mock_launch.call_args
            assert call_kwargs.kwargs["proxy"] == "http://user:pass@proxy:8080"

    @pytest.mark.asyncio
    async def test_launch_with_humanize(self):
        session = BrowserSession()
        cfg = SessionConfig(humanize=True, human_preset="careful")

        with patch("cloakbrowsermcp.session.launch_async") as mock_launch:
            mock_browser = AsyncMock()
            mock_launch.return_value = mock_browser

            await session.launch(cfg)

            call_kwargs = mock_launch.call_args
            assert call_kwargs.kwargs["humanize"] is True
            assert call_kwargs.kwargs["human_preset"] == "careful"

    @pytest.mark.asyncio
    async def test_launch_persistent_context(self):
        session = BrowserSession()
        cfg = SessionConfig(user_data_dir="/tmp/profile")

        with patch("cloakbrowsermcp.session.launch_persistent_context_async") as mock_launch:
            mock_ctx = AsyncMock()
            mock_launch.return_value = mock_ctx

            await session.launch(cfg)

            assert session.is_running is True
            mock_launch.assert_called_once()

    @pytest.mark.asyncio
    async def test_launch_with_fingerprint_seed(self):
        session = BrowserSession()
        cfg = SessionConfig(fingerprint_seed="42069")

        with patch("cloakbrowsermcp.session.launch_async") as mock_launch:
            mock_browser = AsyncMock()
            mock_launch.return_value = mock_browser

            await session.launch(cfg)

            call_kwargs = mock_launch.call_args
            args_list = call_kwargs.kwargs.get("args", [])
            assert "--fingerprint=42069" in args_list

    @pytest.mark.asyncio
    async def test_close_stops_browser(self):
        session = BrowserSession()
        cfg = SessionConfig()

        with patch("cloakbrowsermcp.session.launch_async") as mock_launch:
            mock_browser = AsyncMock()
            mock_launch.return_value = mock_browser

            await session.launch(cfg)
            await session.close()

            assert session.is_running is False
            mock_browser.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_when_not_running(self):
        session = BrowserSession()
        # Should not raise
        await session.close()

    @pytest.mark.asyncio
    async def test_new_page(self):
        session = BrowserSession()
        cfg = SessionConfig()

        with patch("cloakbrowsermcp.session.launch_async") as mock_launch:
            mock_browser = AsyncMock()
            mock_page = _make_mock_page()

            mock_context = AsyncMock()
            mock_context.new_page = AsyncMock(return_value=mock_page)
            mock_browser.new_context = AsyncMock(return_value=mock_context)

            mock_launch.return_value = mock_browser

            await session.launch(cfg)
            page_id = await session.new_page()

            assert page_id in session.pages
            assert session.pages[page_id] is mock_page
            # Console capture should be set up
            assert mock_page.on.call_count >= 2  # console + pageerror

    @pytest.mark.asyncio
    async def test_close_page(self):
        session = BrowserSession()
        cfg = SessionConfig()

        with patch("cloakbrowsermcp.session.launch_async") as mock_launch:
            mock_browser = AsyncMock()
            mock_page = _make_mock_page()

            mock_context = AsyncMock()
            mock_context.new_page = AsyncMock(return_value=mock_page)
            mock_browser.new_context = AsyncMock(return_value=mock_context)

            mock_launch.return_value = mock_browser

            await session.launch(cfg)
            page_id = await session.new_page()
            await session.close_page(page_id)

            assert page_id not in session.pages
            mock_page.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_page_not_found(self):
        session = BrowserSession()
        with pytest.raises(KeyError, match="no_such_page"):
            await session.close_page("no_such_page")

    @pytest.mark.asyncio
    async def test_get_page(self):
        session = BrowserSession()
        cfg = SessionConfig()

        with patch("cloakbrowsermcp.session.launch_async") as mock_launch:
            mock_browser = AsyncMock()
            mock_page = _make_mock_page()

            mock_context = AsyncMock()
            mock_context.new_page = AsyncMock(return_value=mock_page)
            mock_browser.new_context = AsyncMock(return_value=mock_context)

            mock_launch.return_value = mock_browser

            await session.launch(cfg)
            page_id = await session.new_page()

            assert session.get_page(page_id) is mock_page

    @pytest.mark.asyncio
    async def test_get_page_not_found(self):
        session = BrowserSession()
        with pytest.raises(KeyError, match="no_such_page"):
            session.get_page("no_such_page")


class TestRefManagement:
    """Test ref ID storage and retrieval."""

    def test_set_and_get_refs(self):
        session = BrowserSession()
        refs = {
            "e1": {"selector": "button#submit", "tag": "button"},
            "e2": {"selector": "input#email", "tag": "input"},
        }
        session.set_refs("page_001", refs)

        assert session.get_refs("page_001") == refs

    def test_get_refs_empty_page(self):
        session = BrowserSession()
        assert session.get_refs("nonexistent") == {}

    @pytest.mark.asyncio
    async def test_refs_cleared_on_close(self):
        session = BrowserSession()
        cfg = SessionConfig()

        with patch("cloakbrowsermcp.session.launch_async") as mock_launch:
            mock_browser = AsyncMock()
            mock_launch.return_value = mock_browser

            await session.launch(cfg)

            session.set_refs("page_001", {"e1": {"selector": "x"}})
            await session.close()

            assert session.get_refs("page_001") == {}


class TestConsoleCapture:
    """Test console message capture."""

    def test_console_messages_empty_by_default(self):
        session = BrowserSession()
        assert session.get_console_messages("page_001") == []

    def test_clear_console_messages(self):
        session = BrowserSession()
        session._console_messages["page_001"] = [
            {"type": "log", "text": "hello"},
        ]
        session.clear_console_messages("page_001")
        assert session.get_console_messages("page_001") == []
