# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Tests for TurnoverCoordinator."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from freezegun import freeze_time
from homeassistant.components.calendar import CalendarEvent
from homeassistant.core import Event
from homeassistant.exceptions import HomeAssistantError

from custom_components.turnovercal.const import (
    DEFAULT_SUMMARY_PREFIX,
    DEFAULT_TRAILING_DURATION_HOURS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    EVENT_KEYMASTER,
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
        first_add_count = cache.async_add_event.call_count
        assert first_add_count >= 1

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


# ---------------------------------------------------------------------------
# TurnoverCoordinator - cache preservation of past events
# ---------------------------------------------------------------------------

_FROZEN_MARCH_15 = "2026-03-15T12:00:00-04:00"


class TestCoordinatorCachePreservation:
    """Tests for coordinator preservation of past cached events."""

    async def test_past_turnover_preserved_when_rc_removes_source(
        self, hass: HomeAssistant
    ) -> None:
        """Past turnover stays in cache when RC source expires."""
        past_event = TurnoverEvent(
            uid="0123456789abcdef@turnovercal.homeassistant",
            summary="Turnover - Beach House",
            dtstart=_dt(10, 11),
            dtend=_dt(10, 15),
            timezone="America/New_York",
            source_checkout_id="src-001",
            source_checkin_id="src-002",
            created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        )

        mock_entity = MagicMock()
        mock_entity.async_get_events = AsyncMock(return_value=[])

        cache = MagicMock(spec=EventCache)
        cache.get_events.return_value = {
            past_event.uid: past_event,
        }
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
            update_interval=timedelta(
                minutes=DEFAULT_UPDATE_INTERVAL,
            ),
        )

        with (
            freeze_time(_FROZEN_MARCH_15),
            patch(
                "custom_components.turnovercal.coordinator.compute_turnover_events",
                return_value=[],
            ),
        ):
            await coordinator._async_update_data()  # noqa: SLF001

        cache.async_remove_event.assert_not_called()

    async def test_future_turnover_removed_when_cancelled(
        self, hass: HomeAssistant
    ) -> None:
        """Future turnover is removed when guest cancels."""
        future_event = TurnoverEvent(
            uid="abcdef0123456789@turnovercal.homeassistant",
            summary="Turnover - Beach House",
            dtstart=_dt(20, 11),
            dtend=_dt(20, 15),
            timezone="America/New_York",
            source_checkout_id="src-003",
            source_checkin_id="src-004",
            created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        )

        mock_entity = MagicMock()
        mock_entity.async_get_events = AsyncMock(return_value=[])

        cache = MagicMock(spec=EventCache)
        cache.get_events.return_value = {
            future_event.uid: future_event,
        }
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
            update_interval=timedelta(
                minutes=DEFAULT_UPDATE_INTERVAL,
            ),
        )

        with (
            freeze_time(_FROZEN_MARCH_15),
            patch(
                "custom_components.turnovercal.coordinator.compute_turnover_events",
                return_value=[],
            ),
        ):
            await coordinator._async_update_data()  # noqa: SLF001

        cache.async_remove_event.assert_called_once_with(
            future_event.uid,
        )

    async def test_past_future_split_mixed(self, hass: HomeAssistant) -> None:
        """Past events preserved, future events removed."""
        past_event = TurnoverEvent(
            uid="0123456789abcdef@turnovercal.homeassistant",
            summary="Turnover - Beach House",
            dtstart=_dt(10, 11),
            dtend=_dt(10, 15),
            timezone="America/New_York",
            source_checkout_id="src-001",
            source_checkin_id="src-002",
            created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        )
        future_event = TurnoverEvent(
            uid="abcdef0123456789@turnovercal.homeassistant",
            summary="Turnover - Beach House",
            dtstart=_dt(20, 11),
            dtend=_dt(20, 15),
            timezone="America/New_York",
            source_checkout_id="src-003",
            source_checkin_id="src-004",
            created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        )

        mock_entity = MagicMock()
        mock_entity.async_get_events = AsyncMock(return_value=[])

        cache = MagicMock(spec=EventCache)
        cache.get_events.return_value = {
            past_event.uid: past_event,
            future_event.uid: future_event,
        }
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
            update_interval=timedelta(
                minutes=DEFAULT_UPDATE_INTERVAL,
            ),
        )

        with (
            freeze_time(_FROZEN_MARCH_15),
            patch(
                "custom_components.turnovercal.coordinator.compute_turnover_events",
                return_value=[],
            ),
        ):
            await coordinator._async_update_data()  # noqa: SLF001

        # Only the future event should be removed
        cache.async_remove_event.assert_called_once_with(
            future_event.uid,
        )


# ---------------------------------------------------------------------------
# Phase 5 helper factories
# ---------------------------------------------------------------------------


def _make_cache_mock(
    events: dict[str, TurnoverEvent] | None = None,
) -> MagicMock:
    """Create a mock EventCache with optional events."""
    cache = MagicMock(spec=EventCache)
    cache.get_events.return_value = events or {}
    cache.async_add_event = AsyncMock()
    cache.async_remove_event = AsyncMock()
    cache.async_save = AsyncMock()
    return cache


def _make_coordinator(
    hass: HomeAssistant,
    cache: MagicMock,
    *,
    grace_hours: int = 2,
    lock_entity_id: str | None = None,
    cleaning_code_slot: int = 0,
) -> TurnoverCoordinator:
    """Create a TurnoverCoordinator with Phase 5 params."""
    mock_entity = MagicMock()
    mock_entity.async_get_events = AsyncMock(return_value=[])
    return TurnoverCoordinator(
        hass=hass,
        calendar_entity=mock_entity,
        cache=cache,
        summary_prefix=DEFAULT_SUMMARY_PREFIX,
        property_name="Beach House",
        trailing_duration_hours=DEFAULT_TRAILING_DURATION_HOURS,
        timezone_str="America/New_York",
        update_interval=timedelta(minutes=DEFAULT_UPDATE_INTERVAL),
        lock_entity_id=lock_entity_id,
        cleaning_code_slot=cleaning_code_slot,
        grace_hours=grace_hours,
    )


def _make_event(  # noqa: PLR0913
    dtstart_day: int,
    dtstart_hour: int,
    dtend_day: int,
    dtend_hour: int,
    *,
    uid: str = "0123456789abcdef@turnovercal.homeassistant",
    is_trailing: bool = False,
) -> TurnoverEvent:
    """Create a March 2026 TurnoverEvent for testing."""
    return TurnoverEvent(
        uid=uid,
        summary="Turnover - Beach House",
        dtstart=_dt(dtstart_day, dtstart_hour),
        dtend=_dt(dtend_day, dtend_hour),
        timezone="America/New_York",
        source_checkout_id="src-001",
        source_checkin_id=None if is_trailing else "src-002",
        created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        is_trailing=is_trailing,
    )


# ---------------------------------------------------------------------------
# T033: Tests for apply_cleaning_signal
# ---------------------------------------------------------------------------


class TestApplyCleaningSignal:
    """Tests for apply_cleaning_signal method."""

    async def test_different_day_shortens_dtend(self, hass: HomeAssistant) -> None:
        """Different-day unlock shortens DTEND to 00:00 next day."""
        event = _make_event(10, 11, 12, 15)
        cache = _make_cache_mock({event.uid: event})
        coordinator = _make_coordinator(hass, cache)

        # Unlock 3/10 14:30 ET = 18:30 UTC
        unlock = datetime(2026, 3, 10, 18, 30, tzinfo=UTC)
        await coordinator.apply_cleaning_signal(unlock)

        assert event.dtend == datetime(2026, 3, 11, 0, 0, tzinfo=ET)

    async def test_same_day_checkin_dtend_unchanged(self, hass: HomeAssistant) -> None:
        """Same-day check-in leaves DTEND unchanged."""
        event = _make_event(10, 11, 10, 15)
        cache = _make_cache_mock({event.uid: event})
        coordinator = _make_coordinator(hass, cache)

        # Unlock 3/10 12:00 ET = 16:00 UTC
        unlock = datetime(2026, 3, 10, 16, 0, tzinfo=UTC)
        await coordinator.apply_cleaning_signal(unlock)

        assert event.dtend == _dt(10, 15)

    async def test_sets_adjusted_by_lock(self, hass: HomeAssistant) -> None:
        """Cleaning signal sets adjusted_by_lock=True."""
        event = _make_event(10, 11, 12, 15)
        cache = _make_cache_mock({event.uid: event})
        coordinator = _make_coordinator(hass, cache)

        unlock = datetime(2026, 3, 10, 18, 30, tzinfo=UTC)
        await coordinator.apply_cleaning_signal(unlock)

        assert event.adjusted_by_lock is True

    async def test_sets_lock_unlock_time(self, hass: HomeAssistant) -> None:
        """Cleaning signal records the unlock timestamp."""
        event = _make_event(10, 11, 12, 15)
        cache = _make_cache_mock({event.uid: event})
        coordinator = _make_coordinator(hass, cache)

        unlock = datetime(2026, 3, 10, 18, 30, tzinfo=UTC)
        await coordinator.apply_cleaning_signal(unlock)

        assert event.lock_unlock_time == unlock

    async def test_sets_adjustment_source(self, hass: HomeAssistant) -> None:
        """Cleaning signal records source as keymaster."""
        event = _make_event(10, 11, 12, 15)
        cache = _make_cache_mock({event.uid: event})
        coordinator = _make_coordinator(hass, cache)

        unlock = datetime(2026, 3, 10, 18, 30, tzinfo=UTC)
        await coordinator.apply_cleaning_signal(unlock)

        assert event.adjustment_source == "keymaster"

    async def test_preserves_original_dtend(self, hass: HomeAssistant) -> None:
        """First adjustment preserves original_dtend."""
        event = _make_event(10, 11, 12, 15)
        original = event.dtend
        cache = _make_cache_mock({event.uid: event})
        coordinator = _make_coordinator(hass, cache)

        unlock = datetime(2026, 3, 10, 18, 30, tzinfo=UTC)
        await coordinator.apply_cleaning_signal(unlock)

        assert event.original_dtend == original

    async def test_sets_status_adjusted(self, hass: HomeAssistant) -> None:
        """Cleaning signal sets status to adjusted."""
        event = _make_event(10, 11, 12, 15)
        cache = _make_cache_mock({event.uid: event})
        coordinator = _make_coordinator(hass, cache)

        unlock = datetime(2026, 3, 10, 18, 30, tzinfo=UTC)
        await coordinator.apply_cleaning_signal(unlock)

        assert event.status == "adjusted"

    async def test_idempotent_second_call_noop(self, hass: HomeAssistant) -> None:
        """Second call on already-adjusted event is a no-op."""
        event = _make_event(10, 11, 12, 15)
        cache = _make_cache_mock({event.uid: event})
        coordinator = _make_coordinator(hass, cache)

        unlock = datetime(2026, 3, 10, 18, 30, tzinfo=UTC)
        await coordinator.apply_cleaning_signal(unlock)

        dtend_after = event.dtend
        cache.async_add_event.reset_mock()

        unlock2 = datetime(2026, 3, 10, 19, 0, tzinfo=UTC)
        await coordinator.apply_cleaning_signal(unlock2)

        assert event.dtend == dtend_after
        cache.async_add_event.assert_not_awaited()

    async def test_saves_to_cache(self, hass: HomeAssistant) -> None:
        """Cleaning signal persists the adjusted event."""
        event = _make_event(10, 11, 12, 15)
        cache = _make_cache_mock({event.uid: event})
        coordinator = _make_coordinator(hass, cache)

        unlock = datetime(2026, 3, 10, 18, 30, tzinfo=UTC)
        await coordinator.apply_cleaning_signal(unlock)

        cache.async_add_event.assert_awaited_once_with(event)

    async def test_no_active_event_returns_false(self, hass: HomeAssistant) -> None:
        """No matching event means no adjustment."""
        cache = _make_cache_mock({})
        coordinator = _make_coordinator(hass, cache)

        unlock = datetime(2026, 3, 10, 18, 30, tzinfo=UTC)
        result = await coordinator.apply_cleaning_signal(
            unlock,
        )

        assert result is False
        cache.async_add_event.assert_not_awaited()


# ---------------------------------------------------------------------------
# T034: Tests for early-unlock grace period
# ---------------------------------------------------------------------------


class TestEarlyUnlockGracePeriod:
    """Tests for early-unlock grace period."""

    async def test_within_grace_moves_dtstart(self, hass: HomeAssistant) -> None:
        """Unlock within grace moves DTSTART to unlock time."""
        event = _make_event(10, 11, 12, 15)
        cache = _make_cache_mock({event.uid: event})
        coordinator = _make_coordinator(hass, cache, grace_hours=2)

        # Unlock 3/10 09:30 ET = 13:30 UTC (within 2hr grace)
        unlock = datetime(2026, 3, 10, 13, 30, tzinfo=UTC)
        await coordinator.apply_cleaning_signal(unlock)

        expected = datetime(2026, 3, 10, 9, 30, tzinfo=ET)
        assert event.dtstart == expected

    async def test_outside_grace_ignored(self, hass: HomeAssistant) -> None:
        """Unlock outside grace period is ignored."""
        event = _make_event(10, 11, 12, 15)
        cache = _make_cache_mock({event.uid: event})
        coordinator = _make_coordinator(hass, cache, grace_hours=2)

        # Unlock 3/10 08:00 ET = 12:00 UTC (>2hr before 11:00)
        unlock = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
        result = await coordinator.apply_cleaning_signal(
            unlock,
        )

        assert result is False
        assert event.dtstart == _dt(10, 11)

    async def test_grace_zero_disables(self, hass: HomeAssistant) -> None:
        """Grace period of 0 disables early-unlock detection."""
        event = _make_event(10, 11, 12, 15)
        cache = _make_cache_mock({event.uid: event})
        coordinator = _make_coordinator(hass, cache, grace_hours=0)

        # Unlock 3/10 10:00 ET = 14:00 UTC (would be in grace)
        unlock = datetime(2026, 3, 10, 14, 0, tzinfo=UTC)
        result = await coordinator.apply_cleaning_signal(
            unlock,
        )

        assert result is False
        assert event.dtstart == _dt(10, 11)

    async def test_preserves_original_dtstart(self, hass: HomeAssistant) -> None:
        """Grace period move preserves original_dtstart."""
        event = _make_event(10, 11, 12, 15)
        original = event.dtstart
        cache = _make_cache_mock({event.uid: event})
        coordinator = _make_coordinator(hass, cache, grace_hours=2)

        unlock = datetime(2026, 3, 10, 13, 30, tzinfo=UTC)
        await coordinator.apply_cleaning_signal(unlock)

        assert event.original_dtstart == original

    async def test_early_unlock_also_shortens_multiday(
        self, hass: HomeAssistant
    ) -> None:
        """Early unlock on multi-day turnover adjusts both ends."""
        event = _make_event(10, 11, 12, 15)
        cache = _make_cache_mock({event.uid: event})
        coordinator = _make_coordinator(hass, cache, grace_hours=2)

        # Unlock 3/10 09:30 ET = 13:30 UTC
        unlock = datetime(2026, 3, 10, 13, 30, tzinfo=UTC)
        await coordinator.apply_cleaning_signal(unlock)

        # DTSTART moved
        assert event.dtstart == datetime(2026, 3, 10, 9, 30, tzinfo=ET)
        # DTEND shortened (different day)
        assert event.dtend == datetime(2026, 3, 11, 0, 0, tzinfo=ET)


# ---------------------------------------------------------------------------
# T035: Tests for Keymaster event listener
# ---------------------------------------------------------------------------


class TestKeymasterEventListener:
    """Tests for Keymaster event listener filtering."""

    async def test_wrong_entity_ignored(self, hass: HomeAssistant) -> None:
        """Unlock from wrong lock entity is ignored."""
        cache = _make_cache_mock({})
        coordinator = _make_coordinator(
            hass,
            cache,
            lock_entity_id="lock.front_door",
            cleaning_code_slot=4,
        )

        lock_event = Event(
            EVENT_KEYMASTER,
            {
                "entity_id": "lock.back_door",
                "state": "unlocked",
                "code_slot_num": 4,
            },
        )

        with patch.object(
            coordinator,
            "apply_cleaning_signal",
            create=True,
            new_callable=AsyncMock,
        ) as mock_signal:
            await coordinator.handle_lock_event(lock_event)
            mock_signal.assert_not_awaited()

    async def test_lock_state_ignored(self, hass: HomeAssistant) -> None:
        """Lock event (not unlock) is ignored."""
        cache = _make_cache_mock({})
        coordinator = _make_coordinator(
            hass,
            cache,
            lock_entity_id="lock.front_door",
            cleaning_code_slot=4,
        )

        lock_event = Event(
            EVENT_KEYMASTER,
            {
                "entity_id": "lock.front_door",
                "state": "locked",
                "code_slot_num": 4,
            },
        )

        with patch.object(
            coordinator,
            "apply_cleaning_signal",
            create=True,
            new_callable=AsyncMock,
        ) as mock_signal:
            await coordinator.handle_lock_event(lock_event)
            mock_signal.assert_not_awaited()

    async def test_wrong_code_slot_ignored(self, hass: HomeAssistant) -> None:
        """Unlock from wrong code slot is ignored."""
        cache = _make_cache_mock({})
        coordinator = _make_coordinator(
            hass,
            cache,
            lock_entity_id="lock.front_door",
            cleaning_code_slot=4,
        )

        lock_event = Event(
            EVENT_KEYMASTER,
            {
                "entity_id": "lock.front_door",
                "state": "unlocked",
                "code_slot_num": 7,
            },
        )

        with patch.object(
            coordinator,
            "apply_cleaning_signal",
            create=True,
            new_callable=AsyncMock,
        ) as mock_signal:
            await coordinator.handle_lock_event(lock_event)
            mock_signal.assert_not_awaited()

    async def test_correct_unlock_triggers_signal(self, hass: HomeAssistant) -> None:
        """Correct unlock triggers apply_cleaning_signal."""
        cache = _make_cache_mock({})
        coordinator = _make_coordinator(
            hass,
            cache,
            lock_entity_id="lock.front_door",
            cleaning_code_slot=4,
        )

        lock_event = Event(
            EVENT_KEYMASTER,
            {
                "entity_id": "lock.front_door",
                "state": "unlocked",
                "code_slot_num": 4,
            },
        )

        with patch.object(
            coordinator,
            "apply_cleaning_signal",
            create=True,
            new_callable=AsyncMock,
        ) as mock_signal:
            await coordinator.handle_lock_event(lock_event)
            mock_signal.assert_awaited_once()

    async def test_lock_event_updates_coordinator_data(
        self, hass: HomeAssistant
    ) -> None:
        """Successful lock event updates coordinator data."""
        event = _make_event(10, 11, 12, 15)
        cache = _make_cache_mock({event.uid: event})
        coordinator = _make_coordinator(
            hass,
            cache,
            lock_entity_id="lock.front_door",
            cleaning_code_slot=4,
        )

        lock_event = Event(
            EVENT_KEYMASTER,
            {
                "entity_id": "lock.front_door",
                "state": "unlocked",
                "code_slot_num": 4,
            },
        )

        with (
            freeze_time("2026-03-10T18:30:00+00:00"),
            patch.object(
                coordinator,
                "async_set_updated_data",
            ) as mock_set,
        ):
            await coordinator.handle_lock_event(lock_event)
            mock_set.assert_called_once()


# ---------------------------------------------------------------------------
# Coordinator preserves lock-adjusted events during update
# ---------------------------------------------------------------------------


class TestCoordinatorPreservesAdjustments:
    """Tests for preserving lock-adjusted events on update."""

    async def test_adjusted_event_preserved_when_source_unchanged(
        self, hass: HomeAssistant
    ) -> None:
        """Lock-adjusted event kept when source is unchanged."""
        adjusted = _make_event(10, 11, 12, 15)
        adjusted.adjusted_by_lock = True
        adjusted.original_dtend = adjusted.dtend
        adjusted.dtend = datetime(2026, 3, 11, 0, 0, tzinfo=ET)
        adjusted.status = "adjusted"

        cache = _make_cache_mock({adjusted.uid: adjusted})

        unadjusted = _make_event(10, 11, 12, 15)

        coordinator = _make_coordinator(hass, cache)

        with (
            freeze_time("2026-03-10T18:30:00+00:00"),
            patch(
                "custom_components.turnovercal.coordinator.compute_turnover_events",
                return_value=[unadjusted],
            ),
        ):
            await coordinator._async_update_data()  # noqa: SLF001

        cache.async_add_event.assert_not_called()

    async def test_adjusted_event_reset_when_source_changes(
        self, hass: HomeAssistant
    ) -> None:
        """Lock-adjusted event overwritten when source changes."""
        adjusted = _make_event(10, 11, 12, 15)
        adjusted.adjusted_by_lock = True
        adjusted.original_dtend = adjusted.dtend
        adjusted.dtend = datetime(2026, 3, 11, 0, 0, tzinfo=ET)
        adjusted.status = "adjusted"

        cache = _make_cache_mock({adjusted.uid: adjusted})

        # Source changed: checkin moved to 3/13 15:00
        changed = _make_event(10, 11, 13, 15)

        coordinator = _make_coordinator(hass, cache)

        with (
            freeze_time("2026-03-10T18:30:00+00:00"),
            patch(
                "custom_components.turnovercal.coordinator.compute_turnover_events",
                return_value=[changed],
            ),
        ):
            await coordinator._async_update_data()  # noqa: SLF001

        cache.async_add_event.assert_called_once()

    async def test_adjusted_event_preserved_when_source_removed(
        self, hass: HomeAssistant
    ) -> None:
        """Lock-adjusted event survives source booking removal."""
        adjusted = _make_event(10, 11, 12, 15)
        adjusted.adjusted_by_lock = True
        adjusted.original_dtend = adjusted.dtend
        adjusted.dtend = datetime(2026, 3, 11, 0, 0, tzinfo=ET)
        adjusted.status = "adjusted"

        cache = _make_cache_mock({adjusted.uid: adjusted})

        coordinator = _make_coordinator(hass, cache)

        # Source booking removed: compute returns empty list
        with (
            freeze_time("2026-03-10T18:30:00+00:00"),
            patch(
                "custom_components.turnovercal.coordinator.compute_turnover_events",
                return_value=[],
            ),
        ):
            await coordinator._async_update_data()  # noqa: SLF001

        cache.async_remove_event.assert_not_called()


# ---------------------------------------------------------------------------
# T041: Tests for mid-stay cancellation reservation comparison
# ---------------------------------------------------------------------------


def _make_coordinator_with_entry(
    hass: HomeAssistant,
    cache: MagicMock,
    *,
    rc_events: list[CalendarEvent] | None = None,
    config_entry_id: str = "test_entry_123",
) -> TurnoverCoordinator:
    """Create a TurnoverCoordinator with config_entry_id."""
    mock_entity = MagicMock()
    mock_entity.async_get_events = AsyncMock(
        return_value=rc_events if rc_events is not None else [],
    )
    return TurnoverCoordinator(
        hass=hass,
        calendar_entity=mock_entity,
        cache=cache,
        summary_prefix=DEFAULT_SUMMARY_PREFIX,
        property_name="Beach House",
        trailing_duration_hours=DEFAULT_TRAILING_DURATION_HOURS,
        timezone_str="America/New_York",
        update_interval=timedelta(minutes=DEFAULT_UPDATE_INTERVAL),
        config_entry_id=config_entry_id,
    )


class TestMidstayCancellationDetection:
    """Tests for reservation comparison detecting mid-stay cancellations."""

    @freeze_time("2026-03-15T14:00:00-04:00")
    async def test_reservation_removed_during_stay_triggers(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Reservation disappearing mid-stay triggers cancellation."""
        now = datetime(2026, 3, 15, 14, 0, tzinfo=ET)
        stay_start = now - timedelta(hours=4)
        stay_end = now + timedelta(hours=20)

        active_event = CalendarEvent(
            start=stay_start,
            end=stay_end,
            summary="Guest A",
            uid="rc-stay-001",
        )

        cache = _make_cache_mock()
        coordinator = _make_coordinator_with_entry(
            hass,
            cache,
            rc_events=[active_event],
        )

        mock_cleanliness = AsyncMock()
        mock_cleanliness.async_handle_midstay_cancellation = AsyncMock()
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["test_entry_123"] = {
            "cleanliness": mock_cleanliness,
        }

        # First poll: establishes the active stays
        with patch(
            "custom_components.turnovercal.coordinator.compute_turnover_events",
            return_value=[],
        ):
            await coordinator._async_update_data()  # noqa: SLF001

        # Second poll: reservation gone
        with (
            patch.object(
                coordinator._calendar_entity,  # noqa: SLF001
                "async_get_events",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "custom_components.turnovercal.coordinator.compute_turnover_events",
                return_value=[],
            ),
        ):
            await coordinator._async_update_data()  # noqa: SLF001

        mock_cleanliness.async_handle_midstay_cancellation.assert_awaited_once_with(
            stay_start,
        )

    @freeze_time("2026-03-15T14:00:00-04:00")
    async def test_reservation_removed_before_checkin_no_trigger(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Reservation removed before check-in does not trigger."""
        now = datetime(2026, 3, 15, 14, 0, tzinfo=ET)
        future_start = now + timedelta(days=2)
        future_end = now + timedelta(days=5)

        future_event = CalendarEvent(
            start=future_start,
            end=future_end,
            summary="Guest B",
            uid="rc-stay-002",
        )

        cache = _make_cache_mock()
        coordinator = _make_coordinator_with_entry(
            hass,
            cache,
            rc_events=[future_event],
        )

        mock_cleanliness = AsyncMock()
        mock_cleanliness.async_handle_midstay_cancellation = AsyncMock()
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["test_entry_123"] = {
            "cleanliness": mock_cleanliness,
        }

        # First poll
        with patch(
            "custom_components.turnovercal.coordinator.compute_turnover_events",
            return_value=[],
        ):
            await coordinator._async_update_data()  # noqa: SLF001

        # Second poll: reservation gone (pre-arrival)
        with (
            patch.object(
                coordinator._calendar_entity,  # noqa: SLF001
                "async_get_events",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "custom_components.turnovercal.coordinator.compute_turnover_events",
                return_value=[],
            ),
        ):
            await coordinator._async_update_data()  # noqa: SLF001

        mock_cleanliness.async_handle_midstay_cancellation.assert_not_awaited()

    @freeze_time("2026-03-15T14:00:00-04:00")
    async def test_reservation_removed_after_checkout_no_trigger(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Reservation removed after check-out does not trigger."""
        now = datetime(2026, 3, 15, 14, 0, tzinfo=ET)
        past_start = now - timedelta(days=5)
        past_end = now - timedelta(days=2)

        past_event = CalendarEvent(
            start=past_start,
            end=past_end,
            summary="Guest C",
            uid="rc-stay-003",
        )

        cache = _make_cache_mock()
        coordinator = _make_coordinator_with_entry(
            hass,
            cache,
            rc_events=[past_event],
        )

        mock_cleanliness = AsyncMock()
        mock_cleanliness.async_handle_midstay_cancellation = AsyncMock()
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["test_entry_123"] = {
            "cleanliness": mock_cleanliness,
        }

        # First poll
        with patch(
            "custom_components.turnovercal.coordinator.compute_turnover_events",
            return_value=[],
        ):
            await coordinator._async_update_data()  # noqa: SLF001

        # Second poll: past reservation removed
        with (
            patch.object(
                coordinator._calendar_entity,  # noqa: SLF001
                "async_get_events",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "custom_components.turnovercal.coordinator.compute_turnover_events",
                return_value=[],
            ),
        ):
            await coordinator._async_update_data()  # noqa: SLF001

        mock_cleanliness.async_handle_midstay_cancellation.assert_not_awaited()

    @freeze_time("2026-03-15T14:00:00-04:00")
    async def test_first_poll_does_not_trigger(
        self,
        hass: HomeAssistant,
    ) -> None:
        """First poll with no previous data does not trigger."""
        now = datetime(2026, 3, 15, 14, 0, tzinfo=ET)
        active_event = CalendarEvent(
            start=now - timedelta(hours=4),
            end=now + timedelta(hours=20),
            summary="Guest A",
            uid="rc-stay-001",
        )

        cache = _make_cache_mock()
        coordinator = _make_coordinator_with_entry(
            hass,
            cache,
            rc_events=[active_event],
        )

        mock_cleanliness = AsyncMock()
        mock_cleanliness.async_handle_midstay_cancellation = AsyncMock()
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["test_entry_123"] = {
            "cleanliness": mock_cleanliness,
        }

        with patch(
            "custom_components.turnovercal.coordinator.compute_turnover_events",
            return_value=[],
        ):
            await coordinator._async_update_data()  # noqa: SLF001

        mock_cleanliness.async_handle_midstay_cancellation.assert_not_awaited()

    @freeze_time("2026-03-15T14:00:00-04:00")
    async def test_coordinator_flags_created_event(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Coordinator flags the fallback event from cancellation."""
        now = datetime(2026, 3, 15, 14, 0, tzinfo=ET)
        stay_start = now - timedelta(hours=4)
        stay_end = now + timedelta(hours=20)

        active_event = CalendarEvent(
            start=stay_start,
            end=stay_end,
            summary="Guest A",
            uid="rc-stay-001",
        )

        fallback = _make_event(
            15, 14, 15, 18, uid="abcdef0123456789@turnovercal.homeassistant"
        )
        cache = _make_cache_mock()
        cache.get_events.return_value = {}

        coordinator = _make_coordinator_with_entry(
            hass,
            cache,
            rc_events=[active_event],
        )

        mock_cleanliness = AsyncMock()
        mock_cleanliness.async_handle_midstay_cancellation = AsyncMock(
            return_value="abcdef0123456789@turnovercal.homeassistant",
        )
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["test_entry_123"] = {
            "cleanliness": mock_cleanliness,
        }

        with patch(
            "custom_components.turnovercal.coordinator.compute_turnover_events",
            return_value=[],
        ):
            await coordinator._async_update_data()  # noqa: SLF001

        # Make cache return the fallback event for the second poll
        cache.get_events.return_value = {
            "abcdef0123456789@turnovercal.homeassistant": fallback,
        }

        with (
            patch.object(
                coordinator._calendar_entity,  # noqa: SLF001
                "async_get_events",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "custom_components.turnovercal.coordinator.compute_turnover_events",
                return_value=[],
            ),
        ):
            await coordinator._async_update_data()  # noqa: SLF001

        assert fallback.created_from_midstay_cancellation is True

    @freeze_time("2026-03-15T14:00:00-04:00")
    async def test_naive_datetime_event_skipped_from_active(
        self,
        hass: HomeAssistant,
    ) -> None:
        """RC event with naive datetimes does not enter active tracking."""
        naive_ev = MagicMock()
        naive_ev.start = datetime(2026, 3, 14, 10, 0)  # noqa: DTZ001
        naive_ev.end = datetime(2026, 3, 16, 10, 0)  # noqa: DTZ001
        naive_ev.uid = "rc-naive-001"

        cache = _make_cache_mock()
        coordinator = _make_coordinator_with_entry(
            hass,
            cache,
            rc_events=[],
        )

        mock_cleanliness = AsyncMock()
        mock_cleanliness.async_handle_midstay_cancellation = AsyncMock()
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["test_entry_123"] = {
            "cleanliness": mock_cleanliness,
        }

        # First poll with aware event to establish tracking
        aware_ev = CalendarEvent(
            start=datetime(2026, 3, 14, 10, 0, tzinfo=ET),
            end=datetime(2026, 3, 16, 10, 0, tzinfo=ET),
            summary="Aware Guest",
            uid="rc-naive-001",
        )
        with (
            patch.object(
                coordinator._calendar_entity,  # noqa: SLF001
                "async_get_events",
                new=AsyncMock(return_value=[aware_ev]),
            ),
            patch(
                "custom_components.turnovercal.coordinator.compute_turnover_events",
                return_value=[],
            ),
        ):
            await coordinator._async_update_data()  # noqa: SLF001

        # Second poll: same UID returns with naive datetimes
        with (
            patch.object(
                coordinator._calendar_entity,  # noqa: SLF001
                "async_get_events",
                new=AsyncMock(return_value=[naive_ev]),
            ),
            patch(
                "custom_components.turnovercal.coordinator.compute_turnover_events",
                return_value=[],
            ),
        ):
            await coordinator._async_update_data()  # noqa: SLF001

        mock_cleanliness.async_handle_midstay_cancellation.assert_not_awaited()


# ---------------------------------------------------------------------------
# T044: Tests for preserving mid-stay cancellation events in merge
# ---------------------------------------------------------------------------


class TestPreserveMidstayCancellationEvents:
    """Tests for preserving mid-stay cancellation cleaning events."""

    @freeze_time("2026-03-15T14:00:00-04:00")
    async def test_midstay_event_preserved_when_source_removed(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Mid-stay cancellation event survives source disappearing."""
        midstay_event = _make_event(
            15,
            14,
            15,
            18,
            is_trailing=True,
        )
        midstay_event.created_from_midstay_cancellation = True

        cache = _make_cache_mock(
            {midstay_event.uid: midstay_event},
        )
        coordinator = _make_coordinator(hass, cache)

        with patch(
            "custom_components.turnovercal.coordinator.compute_turnover_events",
            return_value=[],
        ):
            await coordinator._async_update_data()  # noqa: SLF001

        cache.async_remove_event.assert_not_called()

    @freeze_time("2026-03-15T14:00:00-04:00")
    async def test_regular_future_event_still_removed(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Regular (non-midstay) future event is removed normally."""
        regular_event = _make_event(
            20,
            11,
            20,
            15,
            is_trailing=True,
        )
        assert not regular_event.created_from_midstay_cancellation

        cache = _make_cache_mock(
            {regular_event.uid: regular_event},
        )
        coordinator = _make_coordinator(hass, cache)

        with patch(
            "custom_components.turnovercal.coordinator.compute_turnover_events",
            return_value=[],
        ):
            await coordinator._async_update_data()  # noqa: SLF001

        cache.async_remove_event.assert_called_once_with(
            regular_event.uid,
        )
