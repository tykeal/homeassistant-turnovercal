# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Data update coordinator for TurnoverCal."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol
from zoneinfo import ZoneInfo

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.turnovercal.const import DOMAIN
from custom_components.turnovercal.models import TurnoverEvent
from custom_components.turnovercal.turnover import compute_turnover_events

if TYPE_CHECKING:
    from homeassistant.components.calendar import CalendarEvent
    from homeassistant.core import HomeAssistant

    from custom_components.turnovercal.event_cache import EventCache


class _CalendarEntityProtocol(Protocol):
    """Protocol for calendar entities that provide async_get_events."""

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
        start = now - timedelta(days=_QUERY_PAST_DAYS)
        end = now + timedelta(days=_QUERY_FUTURE_DAYS)

        try:
            rc_events = await self._calendar_entity.async_get_events(
                self.hass, start, end
            )
        except Exception:  # noqa: BLE001
            _LOGGER.warning(
                "Rental Control calendar unavailable; serving cached data",
                exc_info=True,
            )
            return self._cache.get_events()

        computed = compute_turnover_events(
            events=rc_events,
            summary_prefix=self._summary_prefix,
            property_name=self._property_name,
            trailing_duration_hours=self._trailing_duration_hours,
            timezone_str=self._timezone_str,
        )

        # Build new event map
        new_events = {evt.uid: evt for evt in computed}

        # Get existing cached events
        cached = self._cache.get_events()

        # Remove stale events no longer in computed set
        for uid in list(cached.keys()):
            if uid not in new_events:
                await self._cache.async_remove_event(uid)

        # Add/update only changed events
        for evt in new_events.values():
            cached_evt = cached.get(evt.uid)
            if cached_evt is not None and not _event_changed(cached_evt, evt):
                continue
            await self._cache.async_add_event(evt)

        return self._cache.get_events()
