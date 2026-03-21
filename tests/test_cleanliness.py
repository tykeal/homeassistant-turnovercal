# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Tests for CleanlinessState and CleanlinessStateMachine."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from custom_components.turnovercal.cleanliness import (
    CleanlinessState,
    CleanlinessStateMachine,
)
from custom_components.turnovercal.const import (
    PHASE_AWAITING_CLEANING,
    PHASE_BEING_CLEANED,
    PHASE_CLEAN,
    PHASE_OCCUPIED,
    REASON_CLEANING_DURATION_ELAPSED,
    REASON_GUEST_CHECKIN,
    REASON_STARTUP_RECONCILIATION,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

UTC = ZoneInfo("UTC")
_TEST_ENTRY_ID = "test_entry_123"


def _make_clean_state(
    *,
    entry_id: str = _TEST_ENTRY_ID,
    now: datetime | None = None,
) -> CleanlinessState:
    """Create a default clean CleanlinessState for testing."""
    return CleanlinessState(
        is_dirty=False,
        phase=PHASE_CLEAN,
        last_transition_at=now or datetime(2026, 3, 15, 14, 0, tzinfo=UTC),
        last_transition_reason=REASON_CLEANING_DURATION_ELAPSED,
        config_entry_id=entry_id,
    )


def _make_dirty_state(
    *,
    entry_id: str = _TEST_ENTRY_ID,
    phase: str = PHASE_AWAITING_CLEANING,
    now: datetime | None = None,
) -> CleanlinessState:
    """Create a dirty CleanlinessState for testing."""
    ts = now or datetime(2026, 3, 15, 14, 0, tzinfo=UTC)
    return CleanlinessState(
        is_dirty=True,
        phase=phase,
        last_transition_at=ts,
        last_transition_reason=REASON_GUEST_CHECKIN,
        dirty_since=ts,
        config_entry_id=entry_id,
    )


def _make_mock_store(
    *,
    persisted_state: CleanlinessState | None = None,
) -> MagicMock:
    """Create a mock CleanlinessStateStore for testing."""
    store = MagicMock()
    store.async_load = AsyncMock(return_value=persisted_state)
    store.async_save = AsyncMock()
    return store


# ---------------------------------------------------------------------------
# CleanlinessState - Serialization
# ---------------------------------------------------------------------------


class TestCleanlinessStateSerialization:
    """Tests for CleanlinessState to_dict/from_dict round-trip."""

    def test_round_trip_all_fields_populated(self) -> None:
        """to_dict/from_dict preserves all fields when fully populated."""
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

        data = state.to_dict()
        restored = CleanlinessState.from_dict(data)

        assert restored.is_dirty is True
        assert restored.phase == PHASE_BEING_CLEANED
        assert restored.last_transition_at == datetime(2026, 3, 15, 14, 0, tzinfo=UTC)
        assert restored.last_transition_reason == REASON_GUEST_CHECKIN
        assert restored.timer_target == datetime(2026, 3, 15, 17, 0, tzinfo=UTC)
        assert restored.dirty_since == datetime(2026, 3, 14, 10, 0, tzinfo=UTC)
        assert restored.associated_checkout_time == datetime(
            2026, 3, 15, 11, 0, tzinfo=UTC
        )
        assert restored.config_entry_id == _TEST_ENTRY_ID

    def test_round_trip_optional_fields_none(self) -> None:
        """to_dict/from_dict preserves None for optional fields."""
        state = _make_clean_state()
        data = state.to_dict()
        restored = CleanlinessState.from_dict(data)

        assert restored.is_dirty is False
        assert restored.phase == PHASE_CLEAN
        assert restored.timer_target is None
        assert restored.dirty_since is None
        assert restored.associated_checkout_time is None

    def test_to_dict_datetimes_are_utc_isoformat(self) -> None:
        """to_dict stores UTC datetimes as ISO strings with +00:00."""
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

        data = state.to_dict()

        assert data["last_transition_at"] == "2026-03-15T14:00:00+00:00"
        assert data["timer_target"] == "2026-03-15T17:00:00+00:00"
        assert data["dirty_since"] == "2026-03-14T10:00:00+00:00"
        assert data["associated_checkout_time"] == "2026-03-15T11:00:00+00:00"

    def test_to_dict_none_fields_are_null(self) -> None:
        """to_dict stores None optional fields as null."""
        state = _make_clean_state()
        data = state.to_dict()

        assert data["timer_target"] is None
        assert data["dirty_since"] is None
        assert data["associated_checkout_time"] is None

    def test_to_dict_contains_all_keys(self) -> None:
        """to_dict returns dict with all expected keys."""
        state = _make_clean_state()
        data = state.to_dict()

        expected_keys = {
            "is_dirty",
            "phase",
            "last_transition_at",
            "last_transition_reason",
            "timer_target",
            "dirty_since",
            "associated_checkout_time",
            "config_entry_id",
        }
        assert set(data.keys()) == expected_keys


# ---------------------------------------------------------------------------
# CleanlinessState - Validation
# ---------------------------------------------------------------------------


class TestCleanlinessStateValidation:
    """Tests for CleanlinessState phase validation."""

    def test_valid_phases_accepted(self) -> None:
        """All four valid phases are accepted."""
        for phase in (
            PHASE_CLEAN,
            PHASE_OCCUPIED,
            PHASE_AWAITING_CLEANING,
            PHASE_BEING_CLEANED,
        ):
            state = CleanlinessState(
                is_dirty=phase != PHASE_CLEAN,
                phase=phase,
                last_transition_at=datetime(2026, 3, 15, 14, 0, tzinfo=UTC),
                last_transition_reason=REASON_STARTUP_RECONCILIATION,
                config_entry_id=_TEST_ENTRY_ID,
            )
            assert state.phase == phase

    def test_invalid_phase_raises_value_error(self) -> None:
        """Invalid phase raises ValueError."""
        with pytest.raises(ValueError, match="Invalid phase"):
            CleanlinessState(
                is_dirty=False,
                phase="invalid_phase",
                last_transition_at=datetime(2026, 3, 15, 14, 0, tzinfo=UTC),
                last_transition_reason=REASON_STARTUP_RECONCILIATION,
                config_entry_id=_TEST_ENTRY_ID,
            )


# ---------------------------------------------------------------------------
# CleanlinessState - Default Factory
# ---------------------------------------------------------------------------


class TestCleanlinessStateDefaults:
    """Tests for CleanlinessState default values."""

    def test_optional_fields_default_to_none(self) -> None:
        """Optional fields default to None when not provided."""
        state = _make_clean_state()

        assert state.timer_target is None
        assert state.dirty_since is None
        assert state.associated_checkout_time is None


# ---------------------------------------------------------------------------
# CleanlinessStateMachine - Initialization
# ---------------------------------------------------------------------------


class TestCleanlinessStateMachineInit:
    """Tests for CleanlinessStateMachine initialization."""

    async def test_initialize_creates_default_clean_state(
        self, hass: HomeAssistant
    ) -> None:
        """async_initialize creates default clean state when store empty."""
        store = _make_mock_store(persisted_state=None)

        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )

        await machine.async_initialize()

        assert machine.is_dirty is False
        assert machine.phase == PHASE_CLEAN
        assert machine.state.config_entry_id == _TEST_ENTRY_ID
        assert machine.state.last_transition_reason == REASON_STARTUP_RECONCILIATION
        store.async_save.assert_called_once()

    async def test_initialize_loads_persisted_state(self, hass: HomeAssistant) -> None:
        """async_initialize loads persisted state from store."""
        persisted = _make_dirty_state(phase=PHASE_AWAITING_CLEANING)
        store = _make_mock_store(persisted_state=persisted)

        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )

        await machine.async_initialize()

        assert machine.is_dirty is True
        assert machine.phase == PHASE_AWAITING_CLEANING
        assert machine.state is persisted

    async def test_initialize_does_not_save_when_persisted(
        self, hass: HomeAssistant
    ) -> None:
        """async_initialize does not save when state loaded from store."""
        persisted = _make_clean_state()
        store = _make_mock_store(persisted_state=persisted)

        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )

        await machine.async_initialize()

        store.async_save.assert_not_called()

    async def test_state_property_raises_before_init(self, hass: HomeAssistant) -> None:
        """Accessing state before initialize raises RuntimeError."""
        store = _make_mock_store()

        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )

        with pytest.raises(RuntimeError, match="not initialized"):
            _ = machine.state


# ---------------------------------------------------------------------------
# CleanlinessStateMachine - Shutdown
# ---------------------------------------------------------------------------


class TestCleanlinessStateMachineShutdown:
    """Tests for CleanlinessStateMachine shutdown behavior."""

    async def test_shutdown_safe_with_no_timer(self, hass: HomeAssistant) -> None:
        """async_shutdown is safe when no timer is active."""
        store = _make_mock_store(persisted_state=None)

        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()
        await machine.async_shutdown()  # Should not raise

    async def test_shutdown_cancels_active_timer(self, hass: HomeAssistant) -> None:
        """async_shutdown cancels active timer unsub."""
        store = _make_mock_store(persisted_state=None)

        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()

        # Simulate an active timer
        mock_unsub = MagicMock()
        machine._timer_unsub = mock_unsub  # noqa: SLF001

        await machine.async_shutdown()

        mock_unsub.assert_called_once()
        assert machine._timer_unsub is None  # noqa: SLF001


# ---------------------------------------------------------------------------
# CleanlinessStateMachine - Properties
# ---------------------------------------------------------------------------


class TestCleanlinessStateMachineProperties:
    """Tests for CleanlinessStateMachine property accessors."""

    async def test_is_dirty_reflects_clean_state(self, hass: HomeAssistant) -> None:
        """is_dirty returns False for clean state."""
        store = _make_mock_store(persisted_state=None)

        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()

        assert machine.is_dirty is False

    async def test_is_dirty_reflects_dirty_state(self, hass: HomeAssistant) -> None:
        """is_dirty returns True for dirty state."""
        persisted = _make_dirty_state(phase=PHASE_OCCUPIED)
        store = _make_mock_store(persisted_state=persisted)

        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()

        assert machine.is_dirty is True

    async def test_phase_reflects_state(self, hass: HomeAssistant) -> None:
        """Phase property reflects the current state's phase."""
        persisted = _make_dirty_state(phase=PHASE_OCCUPIED)
        store = _make_mock_store(persisted_state=persisted)

        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()

        assert machine.phase == PHASE_OCCUPIED

    async def test_phase_default_is_clean(self, hass: HomeAssistant) -> None:
        """Default state has phase PHASE_CLEAN."""
        store = _make_mock_store(persisted_state=None)

        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()

        assert machine.phase == PHASE_CLEAN


# ---------------------------------------------------------------------------
# CleanlinessStateMachine - Callbacks
# ---------------------------------------------------------------------------


class TestCleanlinessStateMachineCallbacks:
    """Tests for CleanlinessStateMachine callback registration."""

    async def test_register_callback_returns_unregister(
        self, hass: HomeAssistant
    ) -> None:
        """register_callback returns callable that removes callback."""
        store = _make_mock_store()

        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )

        callback = MagicMock()
        unregister = machine.register_callback(callback)

        assert callback in machine._callbacks  # noqa: SLF001

        unregister()

        assert callback not in machine._callbacks  # noqa: SLF001

    async def test_unregister_callback_removes(self, hass: HomeAssistant) -> None:
        """unregister_callback removes a registered callback."""
        store = _make_mock_store()

        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )

        callback = MagicMock()
        machine.register_callback(callback)
        machine.unregister_callback(callback)

        assert callback not in machine._callbacks  # noqa: SLF001

    async def test_unregister_callback_noop_if_not_registered(
        self, hass: HomeAssistant
    ) -> None:
        """unregister_callback is safe for unregistered callback."""
        store = _make_mock_store()

        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )

        machine.unregister_callback(MagicMock())  # Should not raise

    async def test_register_multiple_callbacks(self, hass: HomeAssistant) -> None:
        """Multiple callbacks can be registered."""
        store = _make_mock_store()

        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )

        cb1 = MagicMock()
        cb2 = MagicMock()
        machine.register_callback(cb1)
        machine.register_callback(cb2)

        assert len(machine._callbacks) == 2  # noqa: SLF001

    async def test_unregister_via_returned_callable_is_idempotent(
        self, hass: HomeAssistant
    ) -> None:
        """Calling unregister twice does not raise."""
        store = _make_mock_store()

        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )

        callback = MagicMock()
        unregister = machine.register_callback(callback)
        unregister()
        unregister()  # Second call should be safe
