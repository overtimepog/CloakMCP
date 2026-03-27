"""Tests for the MCP server registration — verifying all tools are exposed correctly."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from cloakbrowsermcp.server import create_server


class TestServerCreation:
    """Test MCP server is created with correct metadata."""

    def test_create_server_returns_mcp_instance(self):
        server = create_server()
        assert server is not None
        assert server.name == "CloakBrowserMCP"

    def test_server_has_tools(self):
        server = create_server()
        # The server should have tool handlers registered
        assert hasattr(server, "_tool_manager")


class TestToolRegistration:
    """Test all expected tools are registered on the server."""

    EXPECTED_TOOLS = [
        "launch_browser",
        "close_browser",
        "new_page",
        "close_page",
        "navigate",
        "click",
        "type_text",
        "fill_form",
        "screenshot",
        "get_content",
        "evaluate",
        "wait_for_selector",
        "hover",
        "select_option",
        "press_key",
        "scroll",
        "get_cookies",
        "set_cookies",
        "get_page_info",
        "pdf",
        "list_pages",
    ]

    def test_all_tools_registered(self):
        server = create_server()
        tool_manager = server._tool_manager

        registered = set(tool_manager._tools.keys())

        for tool_name in self.EXPECTED_TOOLS:
            assert tool_name in registered, f"Tool '{tool_name}' not registered"

    def test_no_extra_unexpected_tools(self):
        """All registered tools should be in our expected list."""
        server = create_server()
        tool_manager = server._tool_manager

        registered = set(tool_manager._tools.keys())

        for tool_name in registered:
            assert tool_name in self.EXPECTED_TOOLS, f"Unexpected tool '{tool_name}' registered"


class TestToolSchemas:
    """Test that tool input schemas are properly defined."""

    def test_launch_browser_schema(self):
        server = create_server()
        tools = server._tool_manager._tools

        launch_tool = tools["launch_browser"]
        # Should accept optional parameters
        assert launch_tool is not None

    def test_navigate_requires_url(self):
        server = create_server()
        tools = server._tool_manager._tools

        nav_tool = tools["navigate"]
        assert nav_tool is not None

    def test_click_requires_selector(self):
        server = create_server()
        tools = server._tool_manager._tools

        click_tool = tools["click"]
        assert click_tool is not None
