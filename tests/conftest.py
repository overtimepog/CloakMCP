"""Shared test fixtures and configuration for CloakBrowserMCP tests."""

import pytest


@pytest.fixture
def page_id():
    """Standard test page ID."""
    return "page_abc123"


@pytest.fixture
def session_id():
    """Standard test session ID."""
    return "sess_001"
