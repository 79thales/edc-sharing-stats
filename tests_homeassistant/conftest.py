"""Real Home Assistant fixtures for the additive dashboard feature."""

import pytest


@pytest.fixture
def mock_recorder_before_hass(request: pytest.FixtureRequest) -> None:
    """Prepare the database before autouse custom-integration loading creates HA."""
    if "recorder_mock" in request.fixturenames:
        request.getfixturevalue("recorder_db_url")


@pytest.fixture(autouse=True)
def enable_edc_integration(enable_custom_integrations):
    """Load only the repository's integration when requested by a test."""
    yield
