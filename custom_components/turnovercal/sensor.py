# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Sensor platform for TurnoverCal integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.helpers.network import get_url

from custom_components.turnovercal.const import DOMAIN, FEED_URL_PATH

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import (
        AddEntitiesCallback,
    )


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TurnoverCal sensor entities.

    Creates a diagnostic sensor that exposes the iCal feed URL.

    Args:
        hass: Home Assistant instance.
        entry: The config entry being set up.
        async_add_entities: Callback to register entities.

    """
    async_add_entities([TurnoverCalFeedUrlSensor(entry)])


class TurnoverCalFeedUrlSensor(SensorEntity):
    """Sensor that exposes the iCal feed URL."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_icon = "mdi:calendar-export"
    _attr_has_entity_name = True
    _attr_translation_key = "feed_url"

    def __init__(
        self,
        entry: ConfigEntry,
    ) -> None:
        """Initialise the feed URL sensor.

        Args:
            entry: The config entry this sensor belongs to.

        """
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_feed_url"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }

    @property
    def native_value(self) -> str | None:
        """Return the full iCal feed URL.

        Returns:
            The complete feed URL or None if unavailable.

        """
        entry_data = self.hass.data.get(DOMAIN, {}).get(
            self._entry.entry_id,
        )
        if entry_data is None:
            return None

        token = entry_data.get("feed_token")
        if not token:
            return None

        path = FEED_URL_PATH.format(token=token)

        try:
            base_url = get_url(self.hass)
        except Exception:  # noqa: BLE001
            return path

        return f"{base_url.rstrip('/')}{path}"
