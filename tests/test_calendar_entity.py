# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Tests for the TurnoverCal calendar platform entity."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from homeassistant.components.calendar import CalendarEvent

from custom_components.turnovercal.calendar import (
    TurnoverCalCalendarEntity,
    _to_calendar_event,
)
from custom_components.turnovercal.const import DOMAIN
from custom_components.turnovercal.models import TurnoverEvent

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

VALID_UID_1 = "0123456789abcdef@turnovercal.homeassistant"
VALID_UID_2 = "abcdef0123456789@turnovercal.homeassistant"
VALID_UID_3 = "1111111111111111@turnovercal.homeassistant"


def _make_event(
    uid: str = VALID_UID_1,
    *,
    dtstart: datetime | None = None,
    dtend: datetime | None = None,
    summary: str = "Turnover - Beach House",
    is_trailing: bool = False,
) -> TurnoverEvent:
    """Create a TurnoverEvent for testing."""
    return TurnoverEvent(
        uid=uid,
        summary=summary,
        dtstart=dtstart or datetime(2026, 3, 10, 11, 0, tzinfo=UTC),
        dtend=dtend or datetime(2026, 3, 10, 15, 0, tzinfo=UTC),
        timezone="UTC",
        source_checkout_id="src-co-001",
        source_checkin_id=None if is_trailing else "src-ci-002",
        created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        is_trailing=is_trailing,
    )


class _StubEntry:
    """Minimal config entry stub."""

    def __init__(self, entry_id: str = "test_entry_1") -> None:
        """Initialise with a given entry ID."""
        self.entry_id = entry_id


class _StubCoordinator:
    """Minimal coordinator stub with cache_events."""

    def __init__(
        self,
        events: dict[str, TurnoverEvent] | None = None,
    ) -> None:
        """Initialise with optional events dict."""
        self.cache_events: dict[str, TurnoverEvent] = (
            events if events is not None else {}
        )


def _make_entity(
    entry: _StubEntry | None = None,
    coord: _StubCoordinator | None = None,
) -> TurnoverCalCalendarEntity:
    """Create a TurnoverCalCalendarEntity with patched super init."""
    if entry is None:
        entry = _StubEntry()
    if coord is None:
        coord = _StubCoordinator()
    with patch(
        "custom_components.turnovercal.calendar.CoordinatorEntity.__init__",
    ):
        entity = TurnoverCalCalendarEntity(
            entry,  # type: ignore[arg-type]
            coord,  # type: ignore[arg-type]
        )
        entity.coordinator = coord  # type: ignore[assignment]
    return entity


class TestToCalendarEvent:
    """Tests for the _to_calendar_event helper."""

    def test_converts_fields(self) -> None:
        """Converts TurnoverEvent fields to CalendarEvent."""
        evt = _make_event()
        result = _to_calendar_event(evt)

        assert isinstance(result, CalendarEvent)
        assert result.start == evt.dtstart
        assert result.end == evt.dtend
        assert result.summary == evt.summary
        assert result.description == "Cleaning window between guests"
        assert result.uid == evt.uid


class TestCalendarEntityAttributes:
    """Tests for entity metadata attributes."""

    def test_unique_id(self) -> None:
        """Unique ID includes entry ID with _calendar suffix."""
        entity = _make_entity(entry=_StubEntry("my-entry"))

        assert entity.unique_id == "my-entry_calendar"

    def test_translation_key(self) -> None:
        """Translation key is turnover_calendar."""
        entity = _make_entity()

        assert entity.translation_key == "turnover_calendar"

    def test_has_entity_name(self) -> None:
        """Entity uses device-based naming."""
        entity = _make_entity()

        assert entity.has_entity_name is True

    def test_device_info(self) -> None:
        """Entity links to the TurnoverCal device."""
        entity = _make_entity(entry=_StubEntry("dev-entry"))

        assert entity.device_info == {
            "identifiers": {(DOMAIN, "dev-entry")},
        }


class TestCalendarEventProperty:
    """Tests for the event property (current/next event)."""

    def test_returns_none_when_no_events(self) -> None:
        """Returns None when coordinator has no events."""
        entity = _make_entity()

        assert entity.event is None

    def test_returns_active_event(self) -> None:
        """Returns the currently active event."""
        now = datetime.now(tz=UTC)
        evt = _make_event(
            dtstart=now - timedelta(hours=1),
            dtend=now + timedelta(hours=1),
        )
        entity = _make_entity(
            coord=_StubCoordinator({evt.uid: evt}),
        )

        result = entity.event
        assert result is not None
        assert result.uid == evt.uid
        assert result.summary == evt.summary

    def test_returns_next_future_event(self) -> None:
        """Returns the nearest future event when none active."""
        now = datetime.now(tz=UTC)
        far = _make_event(
            VALID_UID_2,
            dtstart=now + timedelta(days=5),
            dtend=now + timedelta(days=5, hours=4),
        )
        near = _make_event(
            VALID_UID_1,
            dtstart=now + timedelta(days=1),
            dtend=now + timedelta(days=1, hours=4),
        )
        entity = _make_entity(
            coord=_StubCoordinator({far.uid: far, near.uid: near}),
        )

        result = entity.event
        assert result is not None
        assert result.uid == near.uid

    def test_returns_none_all_past(self) -> None:
        """Returns None when all events are in the past."""
        now = datetime.now(tz=UTC)
        past = _make_event(
            dtstart=now - timedelta(days=2),
            dtend=now - timedelta(days=1),
        )
        entity = _make_entity(
            coord=_StubCoordinator({past.uid: past}),
        )

        assert entity.event is None

    def test_active_event_takes_priority(self) -> None:
        """Active event is returned over a nearer future event."""
        now = datetime.now(tz=UTC)
        active = _make_event(
            VALID_UID_1,
            dtstart=now - timedelta(hours=1),
            dtend=now + timedelta(hours=1),
        )
        future = _make_event(
            VALID_UID_2,
            dtstart=now + timedelta(minutes=30),
            dtend=now + timedelta(hours=3),
        )
        entity = _make_entity(
            coord=_StubCoordinator(
                {active.uid: active, future.uid: future},
            ),
        )

        result = entity.event
        assert result is not None
        assert result.uid == active.uid


class TestAsyncGetEvents:
    """Tests for async_get_events date-range filtering."""

    @pytest.mark.asyncio
    async def test_returns_events_in_range(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Returns events that overlap with the date range."""
        now = datetime.now(tz=UTC)
        in_range = _make_event(
            VALID_UID_1,
            dtstart=now + timedelta(days=1),
            dtend=now + timedelta(days=1, hours=4),
        )
        out_range = _make_event(
            VALID_UID_2,
            dtstart=now + timedelta(days=10),
            dtend=now + timedelta(days=10, hours=4),
        )
        entity = _make_entity(
            coord=_StubCoordinator(
                {in_range.uid: in_range, out_range.uid: out_range},
            ),
        )

        start = now
        end = now + timedelta(days=3)
        results = await entity.async_get_events(hass, start, end)

        assert len(results) == 1
        assert results[0].uid == in_range.uid

    @pytest.mark.asyncio
    async def test_returns_empty_no_overlap(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Returns empty list when no events overlap range."""
        now = datetime.now(tz=UTC)
        evt = _make_event(
            dtstart=now + timedelta(days=10),
            dtend=now + timedelta(days=10, hours=4),
        )
        entity = _make_entity(
            coord=_StubCoordinator({evt.uid: evt}),
        )

        start = now
        end = now + timedelta(days=3)
        results = await entity.async_get_events(hass, start, end)

        assert results == []

    @pytest.mark.asyncio
    async def test_returns_empty_no_events(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Returns empty list when coordinator has no events."""
        entity = _make_entity()

        now = datetime.now(tz=UTC)
        results = await entity.async_get_events(
            hass,
            now,
            now + timedelta(days=7),
        )

        assert results == []

    @pytest.mark.asyncio
    async def test_partial_overlap_included(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Event partially overlapping range is included."""
        now = datetime.now(tz=UTC)
        evt = _make_event(
            dtstart=now - timedelta(hours=2),
            dtend=now + timedelta(hours=2),
        )
        entity = _make_entity(
            coord=_StubCoordinator({evt.uid: evt}),
        )

        results = await entity.async_get_events(
            hass,
            now,
            now + timedelta(days=7),
        )

        assert len(results) == 1
        assert results[0].uid == evt.uid

    @pytest.mark.asyncio
    async def test_multiple_events_in_range(
        self,
        hass: HomeAssistant,
    ) -> None:
        """All overlapping events are returned."""
        now = datetime.now(tz=UTC)
        evt1 = _make_event(
            VALID_UID_1,
            dtstart=now + timedelta(days=1),
            dtend=now + timedelta(days=1, hours=4),
        )
        evt2 = _make_event(
            VALID_UID_2,
            dtstart=now + timedelta(days=2),
            dtend=now + timedelta(days=2, hours=4),
        )
        evt3 = _make_event(
            VALID_UID_3,
            dtstart=now + timedelta(days=20),
            dtend=now + timedelta(days=20, hours=4),
        )
        entity = _make_entity(
            coord=_StubCoordinator(
                {
                    evt1.uid: evt1,
                    evt2.uid: evt2,
                    evt3.uid: evt3,
                },
            ),
        )

        results = await entity.async_get_events(
            hass,
            now,
            now + timedelta(days=5),
        )

        assert len(results) == 2
        uids = {r.uid for r in results}
        assert uids == {evt1.uid, evt2.uid}
