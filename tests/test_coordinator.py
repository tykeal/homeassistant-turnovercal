# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Tests for TurnoverCoordinator."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from homeassistant.components.calendar import CalendarEvent
from homeassistant.exceptions import HomeAssistantError

from custom_components.turnovercal.const import (
    DEFAULT_SUMMARY_PREFIX,
    DEFAULT_TRAILING_DURATION_HOURS,
    DEFAULT_UPDATE_INTERVAL,
)
from custom_components.turnovercal.coordinator import TurnoverCoordinator
from custom_components.turnovercal.event_cache import EventCache
from custom_components.turnovercal.models import TurnoverEvent

if TYPE_CHECKING:
    import pytest
    from homeassistant.core import HomeAssistant

UTC = ZoneInfo("UTC")
ET = ZoneInfo("America/New_York")


def _cal(
    summary: str,
    start: datetime,
    end: datetime,
) -> CalendarEvent:
    """Create a CalendarEvent helper."""
    return CalendarEvent(start=start, end=end, summary=summary)


def _dt(day: int, hour: int) -> datetime:
    """Create a March 2026 datetime in Eastern time."""
    return datetime(2026, 3, day, hour, 0, tzinfo=ET)


# ---------------------------------------------------------------------------
# TurnoverCoordinator - basic data update
# ---------------------------------------------------------------------------


class TestCoordinatorUpdate:
    """Tests for coordinator data update cycle."""

    async def test_calls_async_get_events(self, hass: HomeAssistant) -> None:
        """Coordinator calls async_get_events on the RC calendar."""
        mock_entity = MagicMock()
        mock_entity.async_get_events = AsyncMock(return_value=[])

        cache = MagicMock(spec=EventCache)
        cache.get_events.return_value = {}
        cache.async_add_event = AsyncMock()
        cache.async_remove_event = AsyncMock()
        cache.async_save = AsyncMock()

        coordinator = TurnoverCoordinator(
            hass=hass,
            calendar_entity=mock_entity,
            cache=cache,
            summary_prefix=DEFAULT_SUMMARY_PREFIX,
            property_name="Beach House",
            trailing_duration_hours=DEFAULT_TRAILING_DURATION_HOURS,
            timezone_str="America/New_York",
            update_interval=timedelta(minutes=DEFAULT_UPDATE_INTERVAL),
        )

        await coordinator._async_update_data()  # noqa: SLF001
        mock_entity.async_get_events.assert_called_once()

    async def test_passes_events_to_compute(self, hass: HomeAssistant) -> None:
        """Coordinator passes RC events to compute_turnover_events."""
        events = [
            _cal("Guest A", _dt(10, 11), _dt(12, 11)),
            _cal("Guest B", _dt(12, 15), _dt(15, 11)),
        ]
        mock_entity = MagicMock()
        mock_entity.async_get_events = AsyncMock(return_value=events)

        cache = MagicMock(spec=EventCache)
        cache.get_events.return_value = {}
        cache.async_add_event = AsyncMock()
        cache.async_remove_event = AsyncMock()
        cache.async_save = AsyncMock()

        coordinator = TurnoverCoordinator(
            hass=hass,
            calendar_entity=mock_entity,
            cache=cache,
            summary_prefix=DEFAULT_SUMMARY_PREFIX,
            property_name="Beach House",
            trailing_duration_hours=DEFAULT_TRAILING_DURATION_HOURS,
            timezone_str="America/New_York",
            update_interval=timedelta(minutes=DEFAULT_UPDATE_INTERVAL),
        )

        with patch(
            "custom_components.turnovercal.coordinator.compute_turnover_events",
            return_value=[],
        ) as mock_compute:
            await coordinator._async_update_data()  # noqa: SLF001
            mock_compute.assert_called_once()
            call_args = mock_compute.call_args
            assert len(call_args.kwargs["events"]) == 2

    async def test_stores_results_in_cache(self, hass: HomeAssistant) -> None:
        """Coordinator stores computed events in cache."""
        events = [_cal("Guest A", _dt(10, 11), _dt(12, 11))]
        mock_entity = MagicMock()
        mock_entity.async_get_events = AsyncMock(return_value=events)

        cache = MagicMock(spec=EventCache)
        cache.get_events.return_value = {}
        cache.async_add_event = AsyncMock()
        cache.async_remove_event = AsyncMock()
        cache.async_save = AsyncMock()

        coordinator = TurnoverCoordinator(
            hass=hass,
            calendar_entity=mock_entity,
            cache=cache,
            summary_prefix=DEFAULT_SUMMARY_PREFIX,
            property_name="Beach House",
            trailing_duration_hours=DEFAULT_TRAILING_DURATION_HOURS,
            timezone_str="America/New_York",
            update_interval=timedelta(minutes=DEFAULT_UPDATE_INTERVAL),
        )

        await coordinator._async_update_data()  # noqa: SLF001
        # Should have added at least the trailing event
        assert cache.async_add_event.call_count >= 1


# ---------------------------------------------------------------------------
# TurnoverCoordinator - periodic update
# ---------------------------------------------------------------------------


class TestCoordinatorPeriodicUpdate:
    """Tests for periodic update behavior."""

    async def test_update_interval_configured(self, hass: HomeAssistant) -> None:
        """Coordinator uses configured update interval."""
        mock_entity = MagicMock()
        mock_entity.async_get_events = AsyncMock(return_value=[])

        cache = MagicMock(spec=EventCache)
        cache.get_events.return_value = {}
        cache.async_save = AsyncMock()

        interval = timedelta(minutes=10)
        coordinator = TurnoverCoordinator(
            hass=hass,
            calendar_entity=mock_entity,
            cache=cache,
            summary_prefix=DEFAULT_SUMMARY_PREFIX,
            property_name="Beach House",
            trailing_duration_hours=DEFAULT_TRAILING_DURATION_HOURS,
            timezone_str="America/New_York",
            update_interval=interval,
        )

        assert coordinator.update_interval == interval


# ---------------------------------------------------------------------------
# TurnoverCoordinator - Rental Control unavailable
# ---------------------------------------------------------------------------


class TestCoordinatorRCUnavailable:
    """Tests for handling Rental Control unavailability."""

    async def test_rc_unavailable_serves_cached_data(self, hass: HomeAssistant) -> None:
        """When RC is unavailable, coordinator serves cached data."""
        mock_entity = MagicMock()
        mock_entity.async_get_events = AsyncMock(
            side_effect=HomeAssistantError("RC unavailable")
        )

        # Simulate existing cached events
        cached_event = TurnoverEvent(
            uid="0123456789abcdef@turnovercal.homeassistant",
            summary="Turnover - Beach House",
            dtstart=_dt(10, 11),
            dtend=_dt(10, 15),
            timezone="America/New_York",
            source_checkout_id="src-001",
            source_checkin_id="src-002",
            created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        )
        cache = MagicMock(spec=EventCache)
        cache.get_events.return_value = {cached_event.uid: cached_event}
        cache.async_save = AsyncMock()

        coordinator = TurnoverCoordinator(
            hass=hass,
            calendar_entity=mock_entity,
            cache=cache,
            summary_prefix=DEFAULT_SUMMARY_PREFIX,
            property_name="Beach House",
            trailing_duration_hours=DEFAULT_TRAILING_DURATION_HOURS,
            timezone_str="America/New_York",
            update_interval=timedelta(minutes=DEFAULT_UPDATE_INTERVAL),
        )

        # Should not raise, should return cached data
        result = await coordinator._async_update_data()  # noqa: SLF001
        assert result is not None

    async def test_rc_unavailable_logs_error(
        self,
        hass: HomeAssistant,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When RC is unavailable, coordinator logs an error."""
        mock_entity = MagicMock()
        mock_entity.async_get_events = AsyncMock(
            side_effect=HomeAssistantError("RC unavailable")
        )

        cache = MagicMock(spec=EventCache)
        cache.get_events.return_value = {}
        cache.async_save = AsyncMock()

        coordinator = TurnoverCoordinator(
            hass=hass,
            calendar_entity=mock_entity,
            cache=cache,
            summary_prefix=DEFAULT_SUMMARY_PREFIX,
            property_name="Beach House",
            trailing_duration_hours=DEFAULT_TRAILING_DURATION_HOURS,
            timezone_str="America/New_York",
            update_interval=timedelta(minutes=DEFAULT_UPDATE_INTERVAL),
        )

        with caplog.at_level(logging.WARNING):
            await coordinator._async_update_data()  # noqa: SLF001

        assert any(
            "unavailable" in msg.lower() or "error" in msg.lower()
            for msg in caplog.messages
        )


# ---------------------------------------------------------------------------
# TurnoverCoordinator - modified guest events
# ---------------------------------------------------------------------------


class TestCoordinatorModifiedEvents:
    """Tests for handling modified guest events."""

    async def test_compute_failure_serves_cached_data(
        self,
        hass: HomeAssistant,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When compute_turnover_events fails, serve cached data."""
        mock_entity = MagicMock()
        mock_entity.async_get_events = AsyncMock(return_value=[])

        cached_event = TurnoverEvent(
            uid="0123456789abcdef@turnovercal.homeassistant",
            summary="Turnover - Beach House",
            dtstart=_dt(10, 11),
            dtend=_dt(10, 15),
            timezone="America/New_York",
            source_checkout_id="src-001",
            source_checkin_id="src-002",
            created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        )
        cache = MagicMock(spec=EventCache)
        cache.get_events.return_value = {
            cached_event.uid: cached_event,
        }
        cache.async_save = AsyncMock()

        coordinator = TurnoverCoordinator(
            hass=hass,
            calendar_entity=mock_entity,
            cache=cache,
            summary_prefix=DEFAULT_SUMMARY_PREFIX,
            property_name="Beach House",
            trailing_duration_hours=DEFAULT_TRAILING_DURATION_HOURS,
            timezone_str="America/New_York",
            update_interval=timedelta(
                minutes=DEFAULT_UPDATE_INTERVAL,
            ),
        )

        with (
            patch(
                "custom_components.turnovercal.coordinator.compute_turnover_events",
                side_effect=ValueError("bad data"),
            ),
            caplog.at_level(logging.WARNING),
        ):
            result = await coordinator._async_update_data()  # noqa: SLF001

        assert cached_event.uid in result
        assert any("computation failed" in msg.lower() for msg in caplog.messages)

    async def test_modified_events_trigger_recalculation(
        self, hass: HomeAssistant
    ) -> None:
        """Modified RC events cause turnover events to be recalculated."""
        # First update with original events
        events_v1 = [
            _cal("Guest A", _dt(10, 11), _dt(12, 11)),
            _cal("Guest B", _dt(12, 15), _dt(15, 11)),
        ]
        mock_entity = MagicMock()
        mock_entity.async_get_events = AsyncMock(return_value=events_v1)

        cache = MagicMock(spec=EventCache)
        cache.get_events.return_value = {}
        cache.async_add_event = AsyncMock()
        cache.async_remove_event = AsyncMock()
        cache.async_save = AsyncMock()

        coordinator = TurnoverCoordinator(
            hass=hass,
            calendar_entity=mock_entity,
            cache=cache,
            summary_prefix=DEFAULT_SUMMARY_PREFIX,
            property_name="Beach House",
            trailing_duration_hours=DEFAULT_TRAILING_DURATION_HOURS,
            timezone_str="America/New_York",
            update_interval=timedelta(minutes=DEFAULT_UPDATE_INTERVAL),
        )

        await coordinator._async_update_data()  # noqa: SLF001
        _first_add_count = cache.async_add_event.call_count

        # Second update with modified events (different times)
        events_v2 = [
            _cal("Guest A", _dt(10, 11), _dt(13, 11)),
            _cal("Guest B", _dt(13, 15), _dt(15, 11)),
        ]
        mock_entity.async_get_events = AsyncMock(return_value=events_v2)
        cache.async_add_event.reset_mock()
        cache.async_remove_event.reset_mock()

        await coordinator._async_update_data()  # noqa: SLF001
        # New events should be added (different UIDs due to different
        # source times)
        assert cache.async_add_event.call_count >= 1
