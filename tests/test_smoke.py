"""Functional smoke test for the distance_from_home custom integration."""
import os
import shutil

import pytest

from homeassistant.const import CONF_API_KEY

pytest_plugins = "pytest_homeassistant_custom_component"

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/DEST_PLACE_ID"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_INTEGRATION_DIR = os.path.join(REPO_ROOT, "custom_components", "distance_from_home")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(hass, enable_custom_integrations):
    dest_dir = hass.config.path("custom_components")
    os.makedirs(dest_dir, exist_ok=True)
    shutil.copytree(
        SRC_INTEGRATION_DIR,
        os.path.join(dest_dir, "distance_from_home"),
        dirs_exist_ok=True,
    )
    yield


async def test_full_flow(hass, aioclient_mock):
    aioclient_mock.get(
        GEOCODE_URL,
        json={"status": "OK", "results": [{"place_id": "ORIGIN_PLACE_ID"}]},
    )

    # --- main config flow: api key ---
    result = await hass.config_entries.flow.async_init(
        "distance_from_home", context={"source": "user"}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "fake_api_key"}
    )
    assert result["type"] == "create_entry", result
    entry = result["result"]
    await hass.async_block_till_done()
    assert entry.state.value == "loaded"

    # --- subentry flow: add a location ---
    aioclient_mock.post(
        ROUTES_URL,
        json={"routes": [{"distanceMeters": 12345, "duration": "600s"}]},
    )

    sub_result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "location"), context={"source": "user"}
    )
    assert sub_result["type"] == "form"

    sub_result = await hass.config_entries.subentries.async_configure(
        sub_result["flow_id"],
        {
            "name": "Work",
            "place_id": "DEST_PLACE_ID",
            "driving": True,
            "walking": True,
            "biking": False,
            "transit": False,
        },
    )
    assert sub_result["type"] == "create_entry", sub_result

    await hass.async_block_till_done()

    # entry should have reloaded and picked up the new subentry
    assert len(entry.subentries) == 1

    driving_state = hass.states.get("sensor.work_driving_distance")
    walking_state = hass.states.get("sensor.work_walking_distance")
    biking_state = hass.states.get("sensor.work_biking_distance")

    assert driving_state is not None, hass.states.async_all()
    assert driving_state.state == "7.67082736816989"  # meters converted to suggested miles display unit
    assert driving_state.attributes["duration_seconds"] == 600
    assert walking_state is not None
    assert biking_state is None  # not enabled for this location

    print("ALL ASSERTIONS PASSED")


async def test_subentry_name_optional_uses_places_api(hass, aioclient_mock):
    """If no name is given, the title should come from the Places API displayName."""
    aioclient_mock.get(
        GEOCODE_URL,
        json={"status": "OK", "results": [{"place_id": "ORIGIN_PLACE_ID"}]},
    )

    result = await hass.config_entries.flow.async_init(
        "distance_from_home", context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "fake_api_key"}
    )
    entry = result["result"]
    await hass.async_block_till_done()

    aioclient_mock.post(
        ROUTES_URL,
        json={"routes": [{"distanceMeters": 12345, "duration": "600s"}]},
    )
    aioclient_mock.get(
        PLACE_DETAILS_URL,
        json={"displayName": {"text": "The Googleplex", "languageCode": "en"}},
    )

    sub_result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "location"), context={"source": "user"}
    )
    sub_result = await hass.config_entries.subentries.async_configure(
        sub_result["flow_id"],
        {
            "place_id": "DEST_PLACE_ID",
            "driving": True,
            "walking": False,
            "biking": False,
            "transit": False,
        },
    )
    assert sub_result["type"] == "create_entry", sub_result
    assert sub_result["title"] == "The Googleplex"

    await hass.async_block_till_done()
    subentry = next(iter(entry.subentries.values()))
    assert subentry.title == "The Googleplex"
    assert "name" not in subentry.data


async def test_subentry_name_lookup_failure_shows_error(hass, aioclient_mock):
    """If the name is omitted and the Places API lookup fails, show an error."""
    aioclient_mock.get(
        GEOCODE_URL,
        json={"status": "OK", "results": [{"place_id": "ORIGIN_PLACE_ID"}]},
    )

    result = await hass.config_entries.flow.async_init(
        "distance_from_home", context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "fake_api_key"}
    )
    entry = result["result"]
    await hass.async_block_till_done()

    aioclient_mock.post(
        ROUTES_URL,
        json={"routes": [{"distanceMeters": 12345, "duration": "600s"}]},
    )
    aioclient_mock.get(
        PLACE_DETAILS_URL,
        status=404,
        json={"error": {"code": 404, "status": "NOT_FOUND", "message": "not found"}},
    )

    sub_result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "location"), context={"source": "user"}
    )
    sub_result = await hass.config_entries.subentries.async_configure(
        sub_result["flow_id"],
        {
            "place_id": "DEST_PLACE_ID",
            "driving": True,
            "walking": False,
            "biking": False,
            "transit": False,
        },
    )
    assert sub_result["type"] == "form"
    assert sub_result["errors"] == {"base": "name_lookup_failed"}


async def test_invalid_api_key_shows_error(hass, aioclient_mock):
    aioclient_mock.get(
        GEOCODE_URL,
        json={"status": "REQUEST_DENIED", "error_message": "bad key"},
    )

    result = await hass.config_entries.flow.async_init(
        "distance_from_home", context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "bad_key"}
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_subentry_requires_at_least_one_mode(hass, aioclient_mock):
    aioclient_mock.get(
        GEOCODE_URL,
        json={"status": "OK", "results": [{"place_id": "ORIGIN_PLACE_ID"}]},
    )

    result = await hass.config_entries.flow.async_init(
        "distance_from_home", context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "fake_api_key"}
    )
    entry = result["result"]
    await hass.async_block_till_done()

    sub_result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "location"), context={"source": "user"}
    )
    sub_result = await hass.config_entries.subentries.async_configure(
        sub_result["flow_id"],
        {
            "name": "Work",
            "place_id": "DEST_PLACE_ID",
            "driving": False,
            "walking": False,
            "biking": False,
            "transit": False,
        },
    )
    assert sub_result["type"] == "form"
    assert sub_result["errors"] == {"base": "no_modes_selected"}


async def test_subentry_invalid_place_id_shows_error(hass, aioclient_mock):
    aioclient_mock.get(
        GEOCODE_URL,
        json={"status": "OK", "results": [{"place_id": "ORIGIN_PLACE_ID"}]},
    )

    result = await hass.config_entries.flow.async_init(
        "distance_from_home", context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "fake_api_key"}
    )
    entry = result["result"]
    await hass.async_block_till_done()

    aioclient_mock.post(
        ROUTES_URL,
        status=400,
        json={"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "bad place id"}},
    )

    sub_result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "location"), context={"source": "user"}
    )
    sub_result = await hass.config_entries.subentries.async_configure(
        sub_result["flow_id"],
        {
            "name": "Work",
            "place_id": "NOT_A_REAL_PLACE",
            "driving": True,
            "walking": False,
            "biking": False,
            "transit": False,
        },
    )
    assert sub_result["type"] == "form"
    assert sub_result["errors"] == {"place_id": "invalid_place_id"}
