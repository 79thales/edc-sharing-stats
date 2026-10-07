"""Real Home Assistant fixtures for the additive dashboard feature."""

import pytest


@pytest.fixture(autouse=True)
def enable_edc_integration(enable_custom_integrations):
    """Load only the repository's integration when requested by a test."""
    yield
