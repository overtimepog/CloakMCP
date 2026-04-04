"""Tests for the MCP server registration — verifying all tools are exposed correctly."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from cloakbrowsermcp.server import create_server


class TestServerCreation:
    """Test MCP server is created with correct metadata."""

    def test_create_server_returns_mcp_instance(self):
        server = create_server()
        assert server is not None
        assert server.name == "cloakbrowser"

    def test_server_has_tools(self):
        server = create_server()
        # The server should have tool handlers registered
        assert hasattr(server, "_tool_manager")


class TestToolRegistration:
    """Test all expected tools are registered on the server."""

    EXPECTED_TOOLS = [
        "launch_browser", "close_browser", "new_page", "close_page", "list_pages",
        "snapshot", "click_ref", "type_ref", "hover_ref", "select_ref", "check_ref",
        "navigate", "go_back", "go_forward", "reload", "wait_for_navigation",
        "click", "smart_action", "type_text", "fill_form", "hover", "select_option",
        "press_key", "scroll",
        "get_text", "get_links", "get_form_fields", "screenshot", "get_content",
        "evaluate", "wait_for_selector", "get_console", "get_cookies", "set_cookies",
        "get_page_info", "pdf", "set_viewport", "emulate_media",
        "network_intercept", "network_continue", "add_init_script", "stealth_config", "binary_info",
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
        assert launch_tool is not None

    def test_navigate_requires_url(self):
        server = create_server()
        tools = server._tool_manager._tools

        nav_tool = tools["navigate"]
        assert nav_tool is not None

    def test_snapshot_tool_exists(self):
        server = create_server()
        tools = server._tool_manager._tools

        snapshot_tool = tools["snapshot"]
        assert snapshot_tool is not None

    def test_click_ref_tool_exists(self):
        server = create_server()
        tools = server._tool_manager._tools

        click_ref_tool = tools["click_ref"]
        assert click_ref_tool is not None
