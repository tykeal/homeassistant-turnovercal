# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Persistent cleanliness state store backed by Home Assistant Store.

Wraps a single ``CleanlinessState`` object with the standard HA
``Store`` persistence pattern, consistent with the existing
``EventCache`` but simplified to a single-object store.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.helpers.storage import Store

from custom_components.turnovercal.cleanliness import CleanlinessState
from custom_components.turnovercal.const import (
    CLEANLINESS_STORE_VERSION,
    DOMAIN,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_SAVE_DELAY = 5


class CleanlinessStateStore:
    """Persistent wrapper for CleanlinessState using HA Store.

    Storage key is ``turnovercal_{entry_id}_cleanliness``.  The store
    version is controlled by ``CLEANLINESS_STORE_VERSION`` in constants.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
    ) -> None:
        """Initialize the cleanliness state store.

        Args:
            hass: Home Assistant instance.
            entry_id: Config entry ID for the storage key.

        """
        self._hass = hass
        self._entry_id = entry_id
        self._store: Store[dict[str, Any]] = Store(
            hass,
            CLEANLINESS_STORE_VERSION,
            f"{DOMAIN}_{entry_id}_cleanliness",
        )

    async def async_load(self) -> CleanlinessState | None:
        """Load the persisted cleanliness state from disk.

        Returns:
            The deserialized ``CleanlinessState``, or ``None`` when
            no persisted state exists.

        """
        raw: dict[str, Any] | None = await self._store.async_load()
        if raw is None:
            return None
        state_data = raw.get("state")
        if state_data is None:
            return None
        return CleanlinessState.from_dict(state_data)

    async def async_save(self, state: CleanlinessState) -> None:
        """Persist the cleanliness state to disk immediately.

        Args:
            state: The CleanlinessState to persist.

        """
        await self._store.async_save(
            {
                "version": CLEANLINESS_STORE_VERSION,
                "state": state.to_dict(),
            }
        )

    def schedule_save(self, state: CleanlinessState) -> None:
        """Schedule a batched save using async_delay_save.

        Uses a 5-second delay to avoid excessive disk writes
        during rapid successive state changes.

        Args:
            state: The CleanlinessState to persist.

        """
        self._store.async_delay_save(
            lambda: {
                "version": CLEANLINESS_STORE_VERSION,
                "state": state.to_dict(),
            },
            _SAVE_DELAY,
        )

    async def async_delete(self) -> None:
        """Remove persisted cleanliness state from disk."""
        await self._store.async_remove()
