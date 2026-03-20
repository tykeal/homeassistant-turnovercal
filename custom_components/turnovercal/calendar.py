# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Calendar platform for TurnoverCal integration."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEvent,
)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from custom_components.turnovercal.const import DOMAIN
from custom_components.turnovercal.coordinator import (
    TurnoverCoordinator,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import (
        AddEntitiesCallback,
    )

    from custom_components.turnovercal.models import TurnoverEvent

_UTC = ZoneInfo("UTC")


def _to_calendar_event(evt: TurnoverEvent) -> CalendarEvent:
    """Convert a TurnoverEvent to a HA CalendarEvent.

    Args:
        evt: The TurnoverEvent to convert.

    Returns:
        A CalendarEvent suitable for the HA calendar dashboard.

    """
    return CalendarEvent(
        start=evt.dtstart,
        end=evt.dtend,
        summary=evt.summary,
        description="Cleaning window between guests",
        uid=evt.uid,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TurnoverCal calendar entity.

    Creates a calendar entity backed by the coordinator's
    cached turnover events.

    Args:
        hass: Home Assistant instance.
        entry: The config entry being set up.
        async_add_entities: Callback to register entities.

    """
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: TurnoverCoordinator = data["coordinator"]
    async_add_entities(
        [TurnoverCalCalendarEntity(entry, coordinator)],
    )


class TurnoverCalCalendarEntity(
    CoordinatorEntity[TurnoverCoordinator],
    CalendarEntity,
):
    """Calendar entity showing turnover cleaning windows."""

    _attr_has_entity_name = True
    _attr_translation_key = "turnover_calendar"

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: TurnoverCoordinator,
    ) -> None:
        """Initialise the turnover calendar entity.

        Args:
            entry: The config entry this entity belongs to.
            coordinator: The data update coordinator.

        """
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_calendar"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
        }

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming or active event.

        Returns:
            The current or next CalendarEvent, or None.

        """
        now = datetime.now(tz=_UTC)
        events = self.coordinator.cache_events
        if not events:
            return None

        # Find active event (happening now)
        for evt in events.values():
            if evt.dtstart <= now <= evt.dtend:
                return _to_calendar_event(evt)

        # Find next future event
        future = [e for e in events.values() if e.dtstart > now]
        if not future:
            return None

        nearest = min(future, key=lambda e: e.dtstart)
        return _to_calendar_event(nearest)

    async def async_get_events(
        self,
        hass: HomeAssistant,  # noqa: ARG002
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return turnover events in a date range.

        Args:
            hass: Home Assistant instance.
            start_date: Range start (inclusive).
            end_date: Range end (exclusive).

        Returns:
            List of CalendarEvents within the range.

        """
        events = self.coordinator.cache_events
        return [
            _to_calendar_event(evt)
            for evt in events.values()
            if evt.dtend > start_date and evt.dtstart < end_date
        ]
