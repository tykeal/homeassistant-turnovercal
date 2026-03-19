# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Persistent event cache backed by Home Assistant Store."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from homeassistant.helpers.storage import Store

from custom_components.turnovercal.const import DOMAIN
from custom_components.turnovercal.models import CachedEventStore, TurnoverEvent

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_STORAGE_VERSION = 1
_SAVE_DELAY = 5


class EventCache:
    """Persistent wrapper around CachedEventStore using HA Store."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        feed_token: str,
    ) -> None:
        """Initialize the event cache.

        Args:
            hass: Home Assistant instance.
            entry_id: Config entry ID for storage key.
            feed_token: Current feed token from config entry data.

        """
        self._hass = hass
        self._entry_id = entry_id
        self._feed_token = feed_token
        self._store: Store[dict[str, Any]] = Store(
            hass,
            _STORAGE_VERSION,
            f"{DOMAIN}_{entry_id}",
        )
        self._data: CachedEventStore | None = None

    async def async_load(self) -> CachedEventStore:
        """Load the cached event store from disk.

        Creates an empty store if no data exists. Always updates
        the feed_token to the current value from config entry data.

        Returns:
            The loaded or newly created CachedEventStore.

        """
        raw: dict[str, Any] | None = await self._store.async_load()
        if raw is not None:
            self._data = CachedEventStore.from_dict(raw)
            self._data.feed_token = self._feed_token
        else:
            self._data = CachedEventStore(
                version=_STORAGE_VERSION,
                events={},
                feed_token=self._feed_token,
                last_cleanup=datetime.now(tz=ZoneInfo("UTC")),
            )
        return self._data

    async def async_save(self) -> None:
        """Persist the cached event store to disk immediately."""
        if self._data is None:
            return
        await self._store.async_save(self._data.to_dict())

    def schedule_save(self) -> None:
        """Schedule a batched save using async_delay_save.

        Useful for rapid successive updates (add/remove) to
        avoid excessive disk writes.
        """
        if self._data is None:
            return
        self._store.async_delay_save(self._data.to_dict, _SAVE_DELAY)

    async def async_add_event(self, event: TurnoverEvent) -> None:
        """Add or update a turnover event in the cache.

        Args:
            event: The TurnoverEvent to store.

        """
        if self._data is None:
            await self.async_load()
        if self._data is None:
            msg = "Failed to load event cache"
            raise RuntimeError(msg)
        self._data.events[event.uid] = event
        self.schedule_save()

    async def async_remove_event(self, uid: str) -> None:
        """Remove a turnover event from the cache by UID.

        No-op if the UID does not exist.

        Args:
            uid: The UID of the event to remove.

        """
        if self._data is None:
            await self.async_load()
        if self._data is None:
            msg = "Failed to load event cache"
            raise RuntimeError(msg)
        self._data.events.pop(uid, None)
        self.schedule_save()

    async def async_cleanup_expired(
        self,
        retention_weeks: int,
        now: datetime | None = None,
    ) -> int:
        """Remove expired cached events.

        Removes events where created_at is older than the retention
        period AND dtend is in the past. Events with future dtend
        are never removed regardless of age.

        Args:
            retention_weeks: Retention period in weeks.
            now: Current time for comparison (default: UTC now).

        Returns:
            Number of events removed.

        """
        if self._data is None:
            await self.async_load()
        if self._data is None:
            msg = "Failed to load event cache"
            raise RuntimeError(msg)

        now_utc = now or datetime.now(tz=ZoneInfo("UTC"))
        cutoff = now_utc - timedelta(weeks=retention_weeks)
        removed = 0

        for uid in list(self._data.events.keys()):
            event = self._data.events[uid]
            if event.created_at < cutoff and event.dtend < now_utc:
                del self._data.events[uid]
                removed += 1

        self._data.last_cleanup = now_utc
        self.schedule_save()
        return removed

    def get_events(self) -> dict[str, TurnoverEvent]:
        """Return all cached turnover events.

        Returns:
            Dictionary mapping UIDs to TurnoverEvent instances.

        """
        if self._data is None:
            return {}
        return self._data.events
