# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Tests for the TurnoverCal feed URL sensor."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from homeassistant.const import EntityCategory

from custom_components.turnovercal.const import DOMAIN, FEED_URL_PATH
from custom_components.turnovercal.sensor import (
    TurnoverCalFeedUrlSensor,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


@pytest.fixture
def fake_entry_data() -> dict[str, object]:
    """Return minimal hass.data entry for a config entry."""
    return {
        "feed_token": "test-token-abc123",
        "coordinator": None,
        "cache": None,
        "timezone_str": "UTC",
        "summary_prefix": "Turnover",
        "property_name": "Beach House",
    }


class _StubEntry:
    """Minimal config entry stub for sensor tests."""

    def __init__(self, entry_id: str = "test_entry_1") -> None:
        """Initialise with a given entry ID."""
        self.entry_id = entry_id


class TestFeedUrlSensor:
    """Tests for TurnoverCalFeedUrlSensor."""

    def test_entity_attributes(self) -> None:
        """Sensor has correct entity category and icon."""
        entry = _StubEntry()
        sensor = TurnoverCalFeedUrlSensor(entry)  # type: ignore[arg-type]

        assert sensor.entity_category == EntityCategory.DIAGNOSTIC
        assert sensor.icon == "mdi:calendar-export"
        assert sensor.has_entity_name is True
        assert sensor.translation_key == "feed_url"

    def test_unique_id(self) -> None:
        """Sensor unique ID includes entry ID."""
        entry = _StubEntry("my-entry-id")
        sensor = TurnoverCalFeedUrlSensor(entry)  # type: ignore[arg-type]

        assert sensor.unique_id == "my-entry-id_feed_url"

    def test_native_value_with_base_url(
        self,
        hass: HomeAssistant,
        fake_entry_data: dict[str, object],
    ) -> None:
        """Sensor returns full URL when get_url succeeds."""
        entry = _StubEntry()
        sensor = TurnoverCalFeedUrlSensor(entry)  # type: ignore[arg-type]
        sensor.hass = hass

        hass.data[DOMAIN] = {entry.entry_id: fake_entry_data}

        with patch(
            "custom_components.turnovercal.sensor.get_url",
            return_value="http://homeassistant.local:8123",
        ):
            value = sensor.native_value

        expected = (
            "http://homeassistant.local:8123"
            "/api/turnovercal/test-token-abc123/calendar.ics"
        )
        assert value == expected

    def test_native_value_strips_trailing_slash(
        self,
        hass: HomeAssistant,
        fake_entry_data: dict[str, object],
    ) -> None:
        """Sensor strips trailing slash from base URL."""
        entry = _StubEntry()
        sensor = TurnoverCalFeedUrlSensor(entry)  # type: ignore[arg-type]
        sensor.hass = hass

        hass.data[DOMAIN] = {entry.entry_id: fake_entry_data}

        with patch(
            "custom_components.turnovercal.sensor.get_url",
            return_value="http://ha.local:8123/",
        ):
            value = sensor.native_value

        assert value is not None
        assert "//api" not in value
        assert "/api/turnovercal/" in value

    def test_native_value_falls_back_to_path(
        self,
        hass: HomeAssistant,
        fake_entry_data: dict[str, object],
    ) -> None:
        """Sensor returns path when get_url raises."""
        entry = _StubEntry()
        sensor = TurnoverCalFeedUrlSensor(entry)  # type: ignore[arg-type]
        sensor.hass = hass

        hass.data[DOMAIN] = {entry.entry_id: fake_entry_data}

        with patch(
            "custom_components.turnovercal.sensor.get_url",
            side_effect=Exception("no URL configured"),
        ):
            value = sensor.native_value

        expected_path = FEED_URL_PATH.format(
            token="test-token-abc123",  # noqa: S106
        )
        assert value == expected_path

    def test_native_value_none_when_no_entry_data(self, hass: HomeAssistant) -> None:
        """Sensor returns None when entry data is missing."""
        entry = _StubEntry()
        sensor = TurnoverCalFeedUrlSensor(entry)  # type: ignore[arg-type]
        sensor.hass = hass

        hass.data[DOMAIN] = {}

        assert sensor.native_value is None

    def test_native_value_none_when_no_domain_data(self, hass: HomeAssistant) -> None:
        """Sensor returns None when domain not in hass.data."""
        entry = _StubEntry()
        sensor = TurnoverCalFeedUrlSensor(entry)  # type: ignore[arg-type]
        sensor.hass = hass

        assert sensor.native_value is None

    def test_native_value_none_when_token_empty(self, hass: HomeAssistant) -> None:
        """Sensor returns None when feed_token is empty."""
        entry = _StubEntry()
        sensor = TurnoverCalFeedUrlSensor(entry)  # type: ignore[arg-type]
        sensor.hass = hass

        hass.data[DOMAIN] = {
            entry.entry_id: {"feed_token": ""},
        }

        assert sensor.native_value is None

    def test_native_value_updates_after_token_change(
        self,
        hass: HomeAssistant,
        fake_entry_data: dict[str, object],
    ) -> None:
        """Sensor reflects token changes in hass.data."""
        entry = _StubEntry()
        sensor = TurnoverCalFeedUrlSensor(entry)  # type: ignore[arg-type]
        sensor.hass = hass

        hass.data[DOMAIN] = {entry.entry_id: fake_entry_data}

        with patch(
            "custom_components.turnovercal.sensor.get_url",
            return_value="http://ha.local:8123",
        ):
            value1 = sensor.native_value

        # Simulate token regeneration
        fake_entry_data["feed_token"] = "new-token-xyz789"  # noqa: S105

        with patch(
            "custom_components.turnovercal.sensor.get_url",
            return_value="http://ha.local:8123",
        ):
            value2 = sensor.native_value

        assert value1 != value2
        assert "new-token-xyz789" in value2  # type: ignore[operator]
