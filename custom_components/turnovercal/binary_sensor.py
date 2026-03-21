# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Binary sensor platform for the TurnoverCal integration.

Provides the ``TurnoverCalCleanlinessSensor`` entity that reports
whether a property is currently dirty (``on``) or clean (``off``).
The sensor reads from the ``CleanlinessStateMachine`` and exposes
lifecycle phase details as extra state attributes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.restore_state import RestoreEntity

from custom_components.turnovercal.const import DOMAIN

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from custom_components.turnovercal.cleanliness import (
        CleanlinessStateMachine,
    )

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TurnoverCal binary sensor entities.

    Creates the cleanliness binary sensor that reports dirty/clean
    state for the configured property.

    Args:
        hass: Home Assistant instance.
        entry: The config entry being set up.
        async_add_entities: Callback to add entities.

    """
    data = hass.data[DOMAIN][entry.entry_id]
    state_machine: CleanlinessStateMachine = data["cleanliness"]
    async_add_entities([TurnoverCalCleanlinessSensor(entry, state_machine)])


class TurnoverCalCleanlinessSensor(RestoreEntity, BinarySensorEntity):
    """Binary sensor indicating whether a property needs cleaning.

    Reports ``on`` when the property is dirty (problem detected) and
    ``off`` when clean. Exposes the cleanliness lifecycle phase and
    transition metadata as extra state attributes.
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_has_entity_name = True
    _attr_translation_key = "dirty"

    def __init__(
        self,
        entry: ConfigEntry,
        state_machine: CleanlinessStateMachine,
    ) -> None:
        """Initialise the cleanliness binary sensor.

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
        self._unregister_callback: Callable[[], None] | None = None

    @property
    def is_on(self) -> bool:
        """Return True if the property is dirty (problem detected).

        Returns:
            True when dirty, False when clean.

        """
        return self._state_machine.is_dirty

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes from the cleanliness state.

        Includes lifecycle phase, transition timestamps, and timer
        information for the dashboard.

        Returns:
            Dictionary of extra attributes.

        """
        state = self._state_machine.state
        return {
            "phase": state.phase,
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
        correct persisted state before the binary-sensor platform loads,
        so ``is_on`` returns the right value immediately.  We keep
        ``RestoreEntity`` as a base class so Home Assistant can show the
        last-known value in the UI while the integration is still
        loading, but the authoritative state always comes from the
        state machine via the ``is_on`` property.
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
