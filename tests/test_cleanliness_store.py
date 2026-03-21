# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Tests for CleanlinessStateStore."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import patch
from zoneinfo import ZoneInfo

from custom_components.turnovercal.cleanliness import CleanlinessState
from custom_components.turnovercal.cleanliness_store import CleanlinessStateStore
from custom_components.turnovercal.const import (
    PHASE_AWAITING_CLEANING,
    PHASE_BEING_CLEANED,
    PHASE_CLEAN,
    REASON_CLEANING_DURATION_ELAPSED,
    REASON_GUEST_CHECKIN,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

UTC = ZoneInfo("UTC")
_TEST_ENTRY_ID = "test_store_entry"


def _make_state(*, is_dirty: bool = False) -> CleanlinessState:
    """Create a CleanlinessState for store testing."""
    if is_dirty:
        return CleanlinessState(
            is_dirty=True,
            phase=PHASE_AWAITING_CLEANING,
            last_transition_at=datetime(2026, 3, 15, 14, 0, tzinfo=UTC),
            last_transition_reason=REASON_GUEST_CHECKIN,
            dirty_since=datetime(2026, 3, 14, 10, 0, tzinfo=UTC),
            config_entry_id=_TEST_ENTRY_ID,
        )
    return CleanlinessState(
        is_dirty=False,
        phase=PHASE_CLEAN,
        last_transition_at=datetime(2026, 3, 15, 14, 0, tzinfo=UTC),
        last_transition_reason=REASON_CLEANING_DURATION_ELAPSED,
        config_entry_id=_TEST_ENTRY_ID,
    )


# ---------------------------------------------------------------------------
# CleanlinessStateStore - Load
# ---------------------------------------------------------------------------


class TestCleanlinessStateStoreLoad:
    """Tests for CleanlinessStateStore async_load."""

    async def test_load_returns_none_when_no_data(self, hass: HomeAssistant) -> None:
        """async_load returns None when no persisted data exists."""
        store = CleanlinessStateStore(hass, _TEST_ENTRY_ID)
        result = await store.async_load()
        assert result is None

    async def test_save_and_load_round_trip_dirty(self, hass: HomeAssistant) -> None:
        """async_save then async_load preserves dirty state data."""
        store = CleanlinessStateStore(hass, _TEST_ENTRY_ID)
        state = _make_state(is_dirty=True)

        await store.async_save(state)

        # New store instance to verify persistence
        store2 = CleanlinessStateStore(hass, _TEST_ENTRY_ID)
        loaded = await store2.async_load()

        assert loaded is not None
        assert loaded.is_dirty is True
        assert loaded.phase == PHASE_AWAITING_CLEANING
        assert loaded.last_transition_reason == REASON_GUEST_CHECKIN
        assert loaded.dirty_since == datetime(2026, 3, 14, 10, 0, tzinfo=UTC)
        assert loaded.config_entry_id == _TEST_ENTRY_ID

    async def test_save_and_load_round_trip_clean(self, hass: HomeAssistant) -> None:
        """Round-trip preserves clean state with None optional fields."""
        store = CleanlinessStateStore(hass, _TEST_ENTRY_ID)
        state = _make_state(is_dirty=False)

        await store.async_save(state)

        store2 = CleanlinessStateStore(hass, _TEST_ENTRY_ID)
        loaded = await store2.async_load()

        assert loaded is not None
        assert loaded.is_dirty is False
        assert loaded.phase == PHASE_CLEAN
        assert loaded.timer_target is None
        assert loaded.dirty_since is None
        assert loaded.associated_checkout_time is None

    async def test_save_and_load_all_optional_fields(self, hass: HomeAssistant) -> None:
        """Round-trip preserves all optional datetime fields."""
        state = CleanlinessState(
            is_dirty=True,
            phase=PHASE_BEING_CLEANED,
            last_transition_at=datetime(2026, 3, 15, 14, 0, tzinfo=UTC),
            last_transition_reason=REASON_GUEST_CHECKIN,
            timer_target=datetime(2026, 3, 15, 17, 0, tzinfo=UTC),
            dirty_since=datetime(2026, 3, 14, 10, 0, tzinfo=UTC),
            associated_checkout_time=datetime(2026, 3, 15, 11, 0, tzinfo=UTC),
            config_entry_id=_TEST_ENTRY_ID,
        )

        store = CleanlinessStateStore(hass, _TEST_ENTRY_ID)
        await store.async_save(state)

        store2 = CleanlinessStateStore(hass, _TEST_ENTRY_ID)
        loaded = await store2.async_load()

        assert loaded is not None
        assert loaded.timer_target == datetime(2026, 3, 15, 17, 0, tzinfo=UTC)
        assert loaded.dirty_since == datetime(2026, 3, 14, 10, 0, tzinfo=UTC)
        assert loaded.associated_checkout_time == datetime(
            2026, 3, 15, 11, 0, tzinfo=UTC
        )


# ---------------------------------------------------------------------------
# CleanlinessStateStore - Schedule Save
# ---------------------------------------------------------------------------


class TestCleanlinessStateStoreScheduleSave:
    """Tests for CleanlinessStateStore schedule_save."""

    async def test_schedule_save_uses_delay_save(self, hass: HomeAssistant) -> None:
        """schedule_save uses async_delay_save for batching writes."""
        store = CleanlinessStateStore(hass, _TEST_ENTRY_ID)
        state = _make_state()

        with patch.object(
            store._store,  # noqa: SLF001
            "async_delay_save",
            wraps=store._store.async_delay_save,  # noqa: SLF001
        ) as mock_delay:
            store.schedule_save(state)
            mock_delay.assert_called_once()


# ---------------------------------------------------------------------------
# CleanlinessStateStore - Delete
# ---------------------------------------------------------------------------


class TestCleanlinessStateStoreDelete:
    """Tests for CleanlinessStateStore async_delete."""

    async def test_delete_removes_persisted_data(self, hass: HomeAssistant) -> None:
        """async_delete removes the persisted state."""
        store = CleanlinessStateStore(hass, _TEST_ENTRY_ID)
        state = _make_state()
        await store.async_save(state)

        # Verify data exists
        loaded = await store.async_load()
        assert loaded is not None

        # Delete
        await store.async_delete()

        # Verify data is gone
        store2 = CleanlinessStateStore(hass, _TEST_ENTRY_ID)
        loaded2 = await store2.async_load()
        assert loaded2 is None

    async def test_delete_is_safe_when_no_data(self, hass: HomeAssistant) -> None:
        """async_delete is safe when no data exists."""
        store = CleanlinessStateStore(hass, _TEST_ENTRY_ID)
        await store.async_delete()  # Should not raise
