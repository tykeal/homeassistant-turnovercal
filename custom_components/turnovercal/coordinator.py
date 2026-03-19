# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Data update coordinator for TurnoverCal."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol
from zoneinfo import ZoneInfo

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.turnovercal.const import (
    DEFAULT_EARLY_UNLOCK_GRACE_HOURS,
    DOMAIN,
)
from custom_components.turnovercal.models import TurnoverEvent
from custom_components.turnovercal.turnover import compute_turnover_events

if TYPE_CHECKING:
    from typing import Any

    from homeassistant.components.calendar import CalendarEvent
    from homeassistant.core import Event, HomeAssistant

    from custom_components.turnovercal.event_cache import EventCache


class _CalendarEntityProtocol(Protocol):
    """Protocol for calendar entities that provide async_get_events."""

    entity_id: str

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start: datetime,
        end: datetime,
    ) -> list[CalendarEvent]:
        """Return events in a time range."""
        ...


_LOGGER = logging.getLogger(__name__)
_QUERY_PAST_DAYS = 7
_QUERY_FUTURE_DAYS = 365


def _event_changed(old: TurnoverEvent, new: TurnoverEvent) -> bool:
    """Check if the meaningful fields of two events differ."""
    return (
        old.summary != new.summary
        or old.dtstart != new.dtstart
        or old.dtend != new.dtend
        or old.source_checkout_id != new.source_checkout_id
        or old.source_checkin_id != new.source_checkin_id
        or old.status != new.status
        or old.is_trailing != new.is_trailing
    )


class TurnoverCoordinator(DataUpdateCoordinator[dict[str, TurnoverEvent]]):
    """Coordinator that polls Rental Control and computes turnovers."""

    def __init__(  # noqa: PLR0913
        self,
        hass: HomeAssistant,
        calendar_entity: _CalendarEntityProtocol,
        cache: EventCache,
        summary_prefix: str,
        property_name: str,
        trailing_duration_hours: int,
        timezone_str: str,
        update_interval: timedelta,
        lock_entity_id: str | None = None,
        cleaning_code_slot: int = 0,
        grace_hours: int = DEFAULT_EARLY_UNLOCK_GRACE_HOURS,
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance.
            calendar_entity: The Rental Control calendar entity.
            cache: The EventCache for persistence.
            summary_prefix: Prefix for turnover event summaries.
            property_name: Name of the property.
            trailing_duration_hours: Hours for trailing turnover window.
            timezone_str: IANA timezone string.
            update_interval: How often to poll for updates.
            lock_entity_id: Keymaster lock entity to monitor.
            cleaning_code_slot: Lock code slot for cleaning staff.
            grace_hours: Early-unlock grace period in hours.

        """
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{property_name}",
            update_interval=update_interval,
        )
        self._calendar_entity = calendar_entity
        self._cache = cache
        self._summary_prefix = summary_prefix
        self._property_name = property_name
        self._trailing_duration_hours = trailing_duration_hours
        self._timezone_str = timezone_str
        self._lock_entity_id = lock_entity_id
        self._cleaning_code_slot = cleaning_code_slot
        self._grace_hours = grace_hours

    @property
    def calendar_entity_id(self) -> str:
        """Return the monitored calendar entity ID."""
        return self._calendar_entity.entity_id

    @property
    def cache_events(self) -> dict[str, TurnoverEvent]:
        """Return current cached events."""
        return self._cache.get_events()

    async def _async_update_data(
        self,
    ) -> dict[str, TurnoverEvent]:
        """Fetch RC events and compute turnovers.

        Queries the Rental Control calendar for events in a window
        from 7 days ago to 365 days in the future. Computes turnover
        events and updates the cache.

        Returns:
            Dictionary of UID to TurnoverEvent.

        Raises:
            No exceptions; returns cached data on failure.

        """
        now = datetime.now(tz=ZoneInfo(self._timezone_str))
        try:
            start = now - timedelta(days=_QUERY_PAST_DAYS)
            end = now + timedelta(days=_QUERY_FUTURE_DAYS)

            rc_events = await self._calendar_entity.async_get_events(
                self.hass, start, end
            )
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Rental Control calendar unavailable; serving cached data",
                exc_info=True,
            )
            return self._cache.get_events()

        try:
            computed = compute_turnover_events(
                events=rc_events,
                summary_prefix=self._summary_prefix,
                property_name=self._property_name,
                trailing_duration_hours=self._trailing_duration_hours,
                timezone_str=self._timezone_str,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Turnover computation failed; serving cached data",
                exc_info=True,
            )
            return self._cache.get_events()

        new_events = {evt.uid: evt for evt in computed}
        await self._merge_events(new_events, now)
        return self._cache.get_events()

    async def _merge_events(
        self,
        new_events: dict[str, TurnoverEvent],
        now: datetime,
    ) -> None:
        """Merge computed events into cache.

        Removes stale future events and adds or updates changed
        events. Preserves lock-adjusted events whose source has
        not changed.

        Args:
            new_events: Freshly computed events keyed by UID.
            now: Current local time for past/future split.

        """
        cached = self._cache.get_events()

        for uid in list(cached.keys()):
            if uid not in new_events:
                cached_evt = cached[uid]
                if cached_evt.dtend > now:
                    await self._cache.async_remove_event(uid)

        for evt in new_events.values():
            existing = cached.get(evt.uid)
            if existing is not None:
                if self._should_keep_adjustment(existing, evt):
                    if self._merge_metadata(existing, evt):
                        await self._cache.async_add_event(existing)
                    continue
                if not _event_changed(existing, evt):
                    continue
            await self._cache.async_add_event(evt)

    @staticmethod
    def _merge_metadata(
        adjusted: TurnoverEvent,
        computed: TurnoverEvent,
    ) -> bool:
        """Copy non-time fields from computed into adjusted event.

        Preserves lock-adjusted times and metadata while updating
        source fields that may have changed (e.g. summary).

        Args:
            adjusted: The lock-adjusted cached event to update.
            computed: The freshly computed event with current data.

        Returns:
            True if any field was changed.

        """
        changed = False
        if adjusted.summary != computed.summary:
            adjusted.summary = computed.summary
            changed = True
        if adjusted.source_checkout_id != computed.source_checkout_id:
            adjusted.source_checkout_id = computed.source_checkout_id
            changed = True
        if adjusted.source_checkin_id != computed.source_checkin_id:
            adjusted.source_checkin_id = computed.source_checkin_id
            changed = True
        if adjusted.is_trailing != computed.is_trailing:
            adjusted.is_trailing = computed.is_trailing
            changed = True
        return changed

    @staticmethod
    def _should_keep_adjustment(
        existing: TurnoverEvent,
        computed: TurnoverEvent,
    ) -> bool:
        """Check if a lock adjustment should be preserved.

        Returns True when the existing event was adjusted by a lock
        and the underlying source event has not changed.

        Args:
            existing: The cached (possibly adjusted) event.
            computed: The freshly computed event.

        Returns:
            True if the adjustment should be kept.

        """
        if not existing.adjusted_by_lock:
            return False
        orig_start = existing.original_dtstart or existing.dtstart
        orig_end = existing.original_dtend or existing.dtend
        return computed.dtstart == orig_start and computed.dtend == orig_end

    def _find_target_event(self, now: datetime) -> TurnoverEvent | None:
        """Find active or upcoming-within-grace turnover event.

        Searches cached events for one whose window contains the
        given time, or whose grace period includes it.

        Args:
            now: Current UTC time.

        Returns:
            The matching TurnoverEvent or None.

        """
        events = self._cache.get_events()
        for evt in events.values():
            if evt.dtstart <= now <= evt.dtend:
                return evt
            if self._grace_hours > 0:
                grace_start = evt.dtstart - timedelta(
                    hours=self._grace_hours,
                )
                if grace_start <= now < evt.dtstart:
                    return evt
        return None

    async def apply_cleaning_signal(
        self,
        now: datetime,
        source: str = "keymaster",
    ) -> bool:
        """Apply a cleaning signal to the active turnover event.

        Finds the active or upcoming-within-grace event and adjusts
        DTEND (shortened to end-of-day) and/or DTSTART (moved to
        unlock time). Sets lock metadata and persists to cache.

        Args:
            now: UTC time of the cleaning signal.
            source: Signal source identifier.

        Returns:
            True if an event was adjusted, False otherwise.

        """
        target = self._find_target_event(now)
        if target is None:
            return False

        if target.adjusted_by_lock:
            return False

        tz = ZoneInfo(self._timezone_str)
        now_local = now.astimezone(tz)

        # Grace period: move DTSTART to unlock time
        if now < target.dtstart:
            if target.original_dtstart is None:
                target.original_dtstart = target.dtstart
            target.dtstart = now_local

        # DTEND shortening: different-day check-in
        if target.dtstart <= now:
            unlock_date = now_local.date()
            checkin_date = target.dtend.date()
            if unlock_date != checkin_date:
                if target.original_dtend is None:
                    target.original_dtend = target.dtend
                next_midnight = (now_local + timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                target.dtend = next_midnight

        target.adjusted_by_lock = True
        target.lock_unlock_time = now
        target.adjustment_source = source
        target.status = "adjusted"

        await self._cache.async_add_event(target)
        return True

    async def handle_lock_event(self, event: Event[Any]) -> None:
        """Handle a Keymaster lock state changed event.

        Filters by entity ID, unlock state, and code slot number.
        On match, applies the cleaning signal to the active
        turnover event.

        Args:
            event: The Keymaster bus event.

        """
        data = event.data
        if data.get("entity_id") != self._lock_entity_id:
            return
        if data.get("state") != "unlocked":
            return
        if data.get("code_slot_num") != self._cleaning_code_slot:
            return

        now = datetime.now(tz=ZoneInfo("UTC"))
        adjusted = await self.apply_cleaning_signal(now)
        if adjusted:
            self.async_set_updated_data(self._cache.get_events())
