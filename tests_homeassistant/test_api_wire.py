"""A05/A06/A07: skutečný aiohttp klient/server, nezávislý očekávaný JSON."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

from aiohttp import ClientSession, web

from custom_components.edc_sharing.api import EdcApiClient, EdcApiError
from custom_components.edc_sharing.calculation import parse_hourly_target_profiles


async def test_minute_boundaries_survive_real_http_and_profile_validation(
    aiohttp_server, socket_enabled
):
    """Skutečný HTTP/JSON průchod syntetickou referencí bez EDC přihlášení.

    Server vrátí minutové hranice, klient projde všemi běžnými kontrolami
    a cílový parser musí zachovat 4 kWh sdílení. HTTP 200 sám není úspěch.
    """
    profile = json.loads((Path(__file__).parents[1] / "tests/fixtures/profile-clock-minutes.json").read_text())
    requests = []

    async def overview(request):
        payload = await request.json()
        requests.append(payload)
        assert payload["dateFrom"] == payload["dateTo"] == "2026-10-13"
        return web.json_response(profile)

    app = web.Application()
    app.router.add_post("/profiles-data/standard/overview", overview)
    server = await aiohttp_server(app)
    async with ClientSession() as session:
        client = EdcApiClient(session, "synthetic-user", "synthetic-password")
        client._store_tokens({"access_token": "synthetic-token", "expires_in": 3600})
        with patch("custom_components.edc_sharing.api.API_BASE_URL", str(server.make_url("/")).rstrip("/")):
            raw = await client.async_get_daily_profile(1, date(2026, 10, 13), date(2026, 10, 14))
    assert raw == profile
    hour, = parse_hourly_target_profiles(raw)
    assert hour.complete and hour.shared == 4 and hour.coverage == 40
    assert len(requests) == 1 and not client.account_state.blocks


async def test_serialized_wire_request_and_rejected_contract(
    aiohttp_server, socket_enabled
):
    requests = []
    reject = False

    async def overview(request):
        payload = await request.json()
        requests.append((payload, dict(request.headers)))
        if reject:
            return web.json_response(
                {
                    "genericError": {
                        "code": "NEW_REQUIRED_FIELD",
                        "message": "synthetic-private-secret",
                    }
                },
                status=400,
            )
        return web.json_response({"valueColumns": [], "content": []})

    app = web.Application()
    app.router.add_post("/profiles-data/standard/overview", overview)
    server = await aiohttp_server(app)
    async with ClientSession() as session:
        client = EdcApiClient(session, "test@example.com", "synthetic-password")
        client._store_tokens({"access_token": "synthetic-token", "expires_in": 3600})
        with patch(
            "custom_components.edc_sharing.api.API_BASE_URL",
            str(server.make_url("/")).rstrip("/"),
        ):
            await client.async_get_daily_profile(1, date(2026, 9, 1), date(2026, 10, 2))
            assert requests[0][0] == {
                "sseId": 1,
                "dateFrom": "2026-09-01",
                "dateTo": "2026-10-01",
                "calculationType": "DAILY",
                "inputData": True,
                "outputData": True,
                "fileName": "_",
            }
            assert requests[0][1]["Edc-Contract-Type"] == "STANDARD"
            assert requests[0][1]["Content-Type"] == "application/json"
            reject = True
            try:
                await client.async_get_daily_profile(
                    1, date(2026, 10, 1), date(2026, 10, 2)
                )
            except EdcApiError as error:
                assert error.status == 400 and error.category == "validation"
                assert "synthetic-private-secret" not in str(error)
            else:
                raise AssertionError("Odmítnutý kontrakt byl vydán za úspěch")
            try:
                await client.async_get_daily_profile(
                    1, date(2026, 10, 1), date(2026, 10, 2)
                )
            except EdcApiError:
                pass
            assert len(requests) == 2
