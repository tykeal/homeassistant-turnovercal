# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Sensor platform for TurnoverCal integration.

Provides the ``TurnoverCalFeedUrlSensor`` diagnostic entity and the
``TurnoverCalCleanlinessSensor`` enum entity that reports the current
cleanliness lifecycle phase.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.helpers.network import get_url
from homeassistant.helpers.restore_state import RestoreEntity

from custom_components.turnovercal.const import (
    DOMAIN,
    FEED_URL_PATH,
    PHASE_AWAITING_CLEANING,
    PHASE_BEING_CLEANED,
    PHASE_CLEAN,
    PHASE_OCCUPIED,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import (
        AddEntitiesCallback,
    )

    from custom_components.turnovercal.cleanliness import (
        CleanlinessStateMachine,
    )

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TurnoverCal sensor entities.

    Creates the diagnostic feed URL sensor and the cleanliness
    enum sensor for the configured property.

    Args:
        hass: Home Assistant instance.
        entry: The config entry being set up.
        async_add_entities: Callback to register entities.

    """
    data = hass.data[DOMAIN][entry.entry_id]
    state_machine: CleanlinessStateMachine = data["cleanliness"]
    async_add_entities(
        [
            TurnoverCalFeedUrlSensor(entry),
            TurnoverCalCleanlinessSensor(entry, state_machine),
        ],
    )


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
            base_url = get_url(self.hass, prefer_external=True)
        except Exception:  # noqa: BLE001
            return path

        return f"{base_url.rstrip('/')}{path}"


class TurnoverCalCleanlinessSensor(RestoreEntity, SensorEntity):
    """Enum sensor reporting the cleanliness lifecycle phase.

    Exposes the current phase as the sensor state and provides
    transition metadata as extra state attributes.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_has_entity_name = True
    _attr_translation_key = "cleanliness"

    def __init__(
        self,
        entry: ConfigEntry,
        state_machine: CleanlinessStateMachine,
    ) -> None:
        """Initialise the cleanliness enum sensor.

        Args:
            entry: The config entry this sensor belongs to.
            state_machine: The cleanliness state machine to read from.

        """
        self._entry = entry
        self._state_machine = state_machine
        self._attr_unique_id = f"{entry.entry_id}_cleanliness"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }
        self._attr_options = [
            PHASE_CLEAN,
            PHASE_OCCUPIED,
            PHASE_AWAITING_CLEANING,
            PHASE_BEING_CLEANED,
        ]
        self._unregister_callback: Callable[[], None] | None = None

    @property
    def native_value(self) -> str:
        """Return the current cleanliness phase.

        Returns:
            The phase string constant.

        """
        return self._state_machine.phase

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes from the cleanliness state.

        Includes transition timestamps and timer information for
        the dashboard.

        Returns:
            Dictionary of extra attributes.

        """
        state = self._state_machine.state
        return {
            "last_transition_at": state.last_transition_at.isoformat(),
            "last_transition_reason": state.last_transition_reason,
            "dirty_since": (
                state.dirty_since.isoformat() if state.dirty_since is not None else None
            ),
            "timer_target": (
                state.timer_target.isoformat()
                if state.timer_target is not None
                else None
            ),
        }

    async def async_added_to_hass(self) -> None:
        """Register state machine callback for live updates.

        The ``CleanlinessStateMachine`` is already initialised with the
        correct persisted state before the sensor platform loads, so
        ``native_value`` returns the right value immediately.  We keep
        ``RestoreEntity`` as a base class so Home Assistant can show the
        last-known value in the UI while the integration is still
        loading, but the authoritative state always comes from the
        state machine via the ``native_value`` property.
        """
        await super().async_added_to_hass()

        self._unregister_callback = self._state_machine.register_callback(
            self.async_write_ha_state,
        )

    async def async_will_remove_from_hass(self) -> None:
        """Unregister state machine callback on entity removal."""
        if self._unregister_callback is not None:
            self._unregister_callback()
            self._unregister_callback = None
