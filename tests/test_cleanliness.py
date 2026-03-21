# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Tests for CleanlinessState and CleanlinessStateMachine."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from custom_components.turnovercal import _async_reconcile_active_stay
from custom_components.turnovercal.cleanliness import (
    CleanlinessState,
    CleanlinessStateMachine,
)
from custom_components.turnovercal.const import (
    EVENT_RC_CHECKIN,
    EVENT_RC_CHECKOUT,
    PHASE_AWAITING_CLEANING,
    PHASE_BEING_CLEANED,
    PHASE_CLEAN,
    PHASE_OCCUPIED,
    REASON_CLEANING_DURATION_ELAPSED,
    REASON_GUEST_CHECKIN,
    REASON_GUEST_CHECKOUT,
    REASON_MID_STAY_CANCELLATION,
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

    def test_naive_last_transition_at_raises_value_error(self) -> None:
        """Naive datetime for last_transition_at raises ValueError."""
        with pytest.raises(ValueError, match="timezone-aware"):
            CleanlinessState(
                is_dirty=False,
                phase=PHASE_CLEAN,
                last_transition_at=datetime(2026, 3, 15, 14, 0),  # noqa: DTZ001
                last_transition_reason=REASON_STARTUP_RECONCILIATION,
                config_entry_id=_TEST_ENTRY_ID,
            )

    def test_naive_timer_target_raises_value_error(self) -> None:
        """Naive datetime for timer_target raises ValueError."""
        with pytest.raises(ValueError, match="timezone-aware"):
            CleanlinessState(
                is_dirty=True,
                phase=PHASE_BEING_CLEANED,
                last_transition_at=datetime(2026, 3, 15, 14, 0, tzinfo=UTC),
                last_transition_reason=REASON_GUEST_CHECKIN,
                timer_target=datetime(2026, 3, 15, 17, 0),  # noqa: DTZ001
                config_entry_id=_TEST_ENTRY_ID,
            )

    def test_naive_dirty_since_raises_value_error(self) -> None:
        """Naive datetime for dirty_since raises ValueError."""
        with pytest.raises(ValueError, match="timezone-aware"):
            CleanlinessState(
                is_dirty=True,
                phase=PHASE_OCCUPIED,
                last_transition_at=datetime(2026, 3, 15, 14, 0, tzinfo=UTC),
                last_transition_reason=REASON_GUEST_CHECKIN,
                dirty_since=datetime(2026, 3, 14, 10, 0),  # noqa: DTZ001
                config_entry_id=_TEST_ENTRY_ID,
            )

    def test_naive_associated_checkout_time_raises_value_error(self) -> None:
        """Naive datetime for associated_checkout_time raises ValueError."""
        with pytest.raises(ValueError, match="timezone-aware"):
            CleanlinessState(
                is_dirty=True,
                phase=PHASE_AWAITING_CLEANING,
                last_transition_at=datetime(2026, 3, 15, 14, 0, tzinfo=UTC),
                last_transition_reason=REASON_GUEST_CHECKIN,
                associated_checkout_time=datetime(2026, 3, 15, 11, 0),  # noqa: DTZ001
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
        store.schedule_save.assert_called_once()

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

    async def test_fire_callbacks_invokes_all(self, hass: HomeAssistant) -> None:
        """_fire_callbacks invokes every registered callback."""
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

        machine._fire_callbacks()  # noqa: SLF001

        cb1.assert_called_once()
        cb2.assert_called_once()

    async def test_fire_callbacks_continues_on_error(self, hass: HomeAssistant) -> None:
        """_fire_callbacks suppresses errors in one callback."""
        store = _make_mock_store()

        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )

        cb_bad = MagicMock(side_effect=RuntimeError("boom"))
        cb_good = MagicMock()
        machine.register_callback(cb_bad)
        machine.register_callback(cb_good)

        machine._fire_callbacks()  # noqa: SLF001

        cb_bad.assert_called_once()
        cb_good.assert_called_once()


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


class TestCleanlinessStateMachinePersistence:
    """Tests for _persist and persistence on transitions."""

    async def test_default_state_creation_persists(self, hass: HomeAssistant) -> None:
        """Creating default clean state calls schedule_save."""
        store = _make_mock_store(persisted_state=None)

        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()

        store.schedule_save.assert_called_once()

    async def test_loaded_state_does_not_persist(self, hass: HomeAssistant) -> None:
        """Loading persisted non-timer state does not call schedule_save."""
        persisted = _make_dirty_state(phase=PHASE_AWAITING_CLEANING)
        store = _make_mock_store(persisted_state=persisted)

        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()

        store.schedule_save.assert_not_called()


# ---------------------------------------------------------------------------
# Restart Persistence
# ---------------------------------------------------------------------------


class TestCleanlinessStateMachineRestartPersistence:
    """Integration tests for state persistence across restarts."""

    async def test_dirty_state_survives_restart(self, hass: HomeAssistant) -> None:
        """Dirty state persists and reloads on second machine instance."""
        dirty = _make_dirty_state(phase=PHASE_AWAITING_CLEANING)
        store = _make_mock_store(persisted_state=dirty)

        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()

        assert machine.is_dirty is True
        assert machine.phase == PHASE_AWAITING_CLEANING

    async def test_being_cleaned_future_timer_reconstitutes(
        self, hass: HomeAssistant
    ) -> None:
        """being_cleaned with future timer_target reconstitutes timer."""
        future_target = datetime(2099, 1, 1, 12, 0, tzinfo=UTC)
        persisted = CleanlinessState(
            is_dirty=True,
            phase=PHASE_BEING_CLEANED,
            last_transition_at=datetime(2099, 1, 1, 9, 0, tzinfo=UTC),
            last_transition_reason=REASON_GUEST_CHECKIN,
            timer_target=future_target,
            dirty_since=datetime(2099, 1, 1, 9, 0, tzinfo=UTC),
            config_entry_id=_TEST_ENTRY_ID,
        )
        store = _make_mock_store(persisted_state=persisted)

        with patch(
            "custom_components.turnovercal.cleanliness.async_track_point_in_time",
        ) as mock_track:
            mock_unsub = MagicMock()
            mock_track.return_value = mock_unsub

            machine = CleanlinessStateMachine(
                hass=hass,
                entry_id=_TEST_ENTRY_ID,
                store=store,
                cleaning_duration_hours=3.0,
            )
            await machine.async_initialize()

            mock_track.assert_called_once()
            call_args = mock_track.call_args
            assert call_args[0][0] is hass
            assert call_args[0][2] == future_target
            assert machine._timer_unsub is mock_unsub  # noqa: SLF001
            assert machine.phase == PHASE_BEING_CLEANED

    async def test_being_cleaned_past_timer_transitions_clean(
        self, hass: HomeAssistant
    ) -> None:
        """Past timer_target transitions to clean immediately on init."""
        past_target = datetime(2020, 1, 1, 12, 0, tzinfo=UTC)
        persisted = CleanlinessState(
            is_dirty=True,
            phase=PHASE_BEING_CLEANED,
            last_transition_at=datetime(2020, 1, 1, 9, 0, tzinfo=UTC),
            last_transition_reason=REASON_GUEST_CHECKIN,
            timer_target=past_target,
            dirty_since=datetime(2020, 1, 1, 9, 0, tzinfo=UTC),
            config_entry_id=_TEST_ENTRY_ID,
        )
        store = _make_mock_store(persisted_state=persisted)

        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()

        assert machine.is_dirty is False
        assert machine.phase == PHASE_CLEAN
        assert machine.state.last_transition_reason == REASON_CLEANING_DURATION_ELAPSED
        store.schedule_save.assert_called_once()

    async def test_timer_expiry_transitions_to_clean_and_persists(
        self, hass: HomeAssistant
    ) -> None:
        """Timer expiry callback transitions to clean and persists."""
        future_target = datetime(2099, 1, 1, 12, 0, tzinfo=UTC)
        persisted = CleanlinessState(
            is_dirty=True,
            phase=PHASE_BEING_CLEANED,
            last_transition_at=datetime(2099, 1, 1, 9, 0, tzinfo=UTC),
            last_transition_reason=REASON_GUEST_CHECKIN,
            timer_target=future_target,
            dirty_since=datetime(2099, 1, 1, 9, 0, tzinfo=UTC),
            config_entry_id=_TEST_ENTRY_ID,
        )
        store = _make_mock_store(persisted_state=persisted)

        captured_cb = None

        def _fake_track(
            _hass: Any,  # noqa: ANN401
            cb: Any,  # noqa: ANN401
            _pt: Any,  # noqa: ANN401
        ) -> MagicMock:
            """Capture the timer callback."""
            nonlocal captured_cb
            captured_cb = cb
            return MagicMock()

        with patch(
            "custom_components.turnovercal.cleanliness.async_track_point_in_time",
            side_effect=_fake_track,
        ):
            machine = CleanlinessStateMachine(
                hass=hass,
                entry_id=_TEST_ENTRY_ID,
                store=store,
                cleaning_duration_hours=3.0,
            )
            await machine.async_initialize()

        assert captured_cb is not None

        await captured_cb(future_target)

        assert machine.is_dirty is False
        assert machine.phase == PHASE_CLEAN
        assert machine.state.last_transition_reason == REASON_CLEANING_DURATION_ELAPSED
        assert machine._timer_unsub is None  # noqa: SLF001
        store.schedule_save.assert_called()

    async def test_timer_expiry_fires_callbacks(self, hass: HomeAssistant) -> None:
        """Timer expiry fires registered callbacks."""
        future_target = datetime(2099, 1, 1, 12, 0, tzinfo=UTC)
        persisted = CleanlinessState(
            is_dirty=True,
            phase=PHASE_BEING_CLEANED,
            last_transition_at=datetime(2099, 1, 1, 9, 0, tzinfo=UTC),
            last_transition_reason=REASON_GUEST_CHECKIN,
            timer_target=future_target,
            dirty_since=datetime(2099, 1, 1, 9, 0, tzinfo=UTC),
            config_entry_id=_TEST_ENTRY_ID,
        )
        store = _make_mock_store(persisted_state=persisted)

        captured_cb = None

        def _fake_track(
            _hass: Any,  # noqa: ANN401
            cb: Any,  # noqa: ANN401
            _pt: Any,  # noqa: ANN401
        ) -> MagicMock:
            """Capture the timer callback."""
            nonlocal captured_cb
            captured_cb = cb
            return MagicMock()

        with patch(
            "custom_components.turnovercal.cleanliness.async_track_point_in_time",
            side_effect=_fake_track,
        ):
            machine = CleanlinessStateMachine(
                hass=hass,
                entry_id=_TEST_ENTRY_ID,
                store=store,
                cleaning_duration_hours=3.0,
            )
            await machine.async_initialize()

        listener = MagicMock()
        machine.register_callback(listener)

        assert captured_cb is not None
        await captured_cb(future_target)

        listener.assert_called_once()

    async def test_past_timer_does_not_schedule_track(
        self, hass: HomeAssistant
    ) -> None:
        """Past timer_target does not call async_track_point_in_time."""
        past_target = datetime(2020, 1, 1, 12, 0, tzinfo=UTC)
        persisted = CleanlinessState(
            is_dirty=True,
            phase=PHASE_BEING_CLEANED,
            last_transition_at=datetime(2020, 1, 1, 9, 0, tzinfo=UTC),
            last_transition_reason=REASON_GUEST_CHECKIN,
            timer_target=past_target,
            dirty_since=datetime(2020, 1, 1, 9, 0, tzinfo=UTC),
            config_entry_id=_TEST_ENTRY_ID,
        )
        store = _make_mock_store(persisted_state=persisted)

        with patch(
            "custom_components.turnovercal.cleanliness.async_track_point_in_time",
        ) as mock_track:
            machine = CleanlinessStateMachine(
                hass=hass,
                entry_id=_TEST_ENTRY_ID,
                store=store,
                cleaning_duration_hours=3.0,
            )
            await machine.async_initialize()

            mock_track.assert_not_called()

    async def test_being_cleaned_no_timer_target_stays_unchanged(
        self, hass: HomeAssistant
    ) -> None:
        """being_cleaned without timer_target loads as-is."""
        persisted = CleanlinessState(
            is_dirty=True,
            phase=PHASE_BEING_CLEANED,
            last_transition_at=datetime(2026, 4, 1, 9, 0, tzinfo=UTC),
            last_transition_reason=REASON_GUEST_CHECKIN,
            dirty_since=datetime(2026, 4, 1, 9, 0, tzinfo=UTC),
            config_entry_id=_TEST_ENTRY_ID,
        )
        store = _make_mock_store(persisted_state=persisted)

        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()

        assert machine.phase == PHASE_BEING_CLEANED
        assert machine.is_dirty is True


# ---------------------------------------------------------------------------
# T020 - async_handle_checkin
# ---------------------------------------------------------------------------


class TestAsyncHandleCheckin:
    """Tests for CleanlinessStateMachine.async_handle_checkin."""

    async def test_clean_to_dirty_occupied(self, hass: HomeAssistant) -> None:
        """Check-in transitions clean→dirty/occupied."""
        store = _make_mock_store(persisted_state=None)
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()
        store.schedule_save.reset_mock()

        checkout = datetime(2026, 3, 20, 11, 0, tzinfo=UTC)
        await machine.async_handle_checkin(checkout)

        assert machine.is_dirty is True
        assert machine.phase == PHASE_OCCUPIED
        assert machine.state.last_transition_reason == REASON_GUEST_CHECKIN
        assert machine.state.associated_checkout_time == checkout
        store.schedule_save.assert_called()

    async def test_idempotent_when_already_occupied(self, hass: HomeAssistant) -> None:
        """Calling checkin when already occupied is a no-op."""
        persisted = _make_dirty_state(phase=PHASE_OCCUPIED)
        store = _make_mock_store(persisted_state=persisted)
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()
        store.schedule_save.reset_mock()

        checkout = datetime(2026, 3, 20, 11, 0, tzinfo=UTC)
        await machine.async_handle_checkin(checkout)

        assert machine.phase == PHASE_OCCUPIED
        store.schedule_save.assert_not_called()

    async def test_being_cleaned_cancels_timer_moves_to_occupied(
        self, hass: HomeAssistant
    ) -> None:
        """Check-in during being_cleaned cancels timer, goes occupied."""
        future_target = datetime(2099, 1, 1, 12, 0, tzinfo=UTC)
        persisted = CleanlinessState(
            is_dirty=True,
            phase=PHASE_BEING_CLEANED,
            last_transition_at=datetime(2099, 1, 1, 9, 0, tzinfo=UTC),
            last_transition_reason=REASON_GUEST_CHECKIN,
            timer_target=future_target,
            dirty_since=datetime(2099, 1, 1, 9, 0, tzinfo=UTC),
            config_entry_id=_TEST_ENTRY_ID,
        )
        store = _make_mock_store(persisted_state=persisted)

        mock_unsub = MagicMock()
        with patch(
            "custom_components.turnovercal.cleanliness.async_track_point_in_time",
            return_value=mock_unsub,
        ):
            machine = CleanlinessStateMachine(
                hass=hass,
                entry_id=_TEST_ENTRY_ID,
                store=store,
                cleaning_duration_hours=3.0,
            )
            await machine.async_initialize()

        checkout = datetime(2099, 1, 5, 11, 0, tzinfo=UTC)
        await machine.async_handle_checkin(checkout)

        mock_unsub.assert_called_once()
        assert machine._timer_unsub is None  # noqa: SLF001
        assert machine.is_dirty is True
        assert machine.phase == PHASE_OCCUPIED

    async def test_checkin_fires_callbacks(self, hass: HomeAssistant) -> None:
        """Check-in fires registered callbacks."""
        store = _make_mock_store(persisted_state=None)
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()

        listener = MagicMock()
        machine.register_callback(listener)

        checkout = datetime(2026, 3, 20, 11, 0, tzinfo=UTC)
        await machine.async_handle_checkin(checkout)

        listener.assert_called_once()


# ---------------------------------------------------------------------------
# T021 - async_handle_checkout
# ---------------------------------------------------------------------------


class TestAsyncHandleCheckout:
    """Tests for CleanlinessStateMachine.async_handle_checkout."""

    async def test_occupied_to_awaiting_cleaning(self, hass: HomeAssistant) -> None:
        """Checkout transitions occupied→awaiting_cleaning."""
        persisted = _make_dirty_state(phase=PHASE_OCCUPIED)
        store = _make_mock_store(persisted_state=persisted)
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()
        store.schedule_save.reset_mock()

        await machine.async_handle_checkout()

        assert machine.is_dirty is True
        assert machine.phase == PHASE_AWAITING_CLEANING
        assert machine.state.last_transition_reason == REASON_GUEST_CHECKOUT
        store.schedule_save.assert_called()

    async def test_noop_when_not_occupied(self, hass: HomeAssistant) -> None:
        """Checkout when not occupied is a no-op."""
        persisted = _make_dirty_state(
            phase=PHASE_AWAITING_CLEANING,
        )
        store = _make_mock_store(persisted_state=persisted)
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()
        store.schedule_save.reset_mock()

        await machine.async_handle_checkout()

        assert machine.phase == PHASE_AWAITING_CLEANING
        store.schedule_save.assert_not_called()

    async def test_noop_when_clean(self, hass: HomeAssistant) -> None:
        """Checkout when clean is a no-op."""
        store = _make_mock_store(persisted_state=None)
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()
        store.schedule_save.reset_mock()

        await machine.async_handle_checkout()

        assert machine.phase == PHASE_CLEAN
        store.schedule_save.assert_not_called()

    async def test_checkout_fires_callbacks(self, hass: HomeAssistant) -> None:
        """Checkout fires registered callbacks."""
        persisted = _make_dirty_state(phase=PHASE_OCCUPIED)
        store = _make_mock_store(persisted_state=persisted)
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()

        listener = MagicMock()
        machine.register_callback(listener)

        await machine.async_handle_checkout()

        listener.assert_called_once()


# ---------------------------------------------------------------------------
# T022 - Cleaning event validation (coverage_checker / fallback_creator)
# ---------------------------------------------------------------------------


class TestCleaningEventValidation:
    """Tests for cleaning event coverage validation on check-in."""

    async def test_checkin_calls_coverage_checker(self, hass: HomeAssistant) -> None:
        """Check-in validates cleaning event coverage."""
        checker = AsyncMock(return_value=True)
        creator = AsyncMock()

        store = _make_mock_store(persisted_state=None)
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
            coverage_checker=checker,
            fallback_creator=creator,
        )
        await machine.async_initialize()

        checkout = datetime(2026, 3, 20, 11, 0, tzinfo=UTC)
        await machine.async_handle_checkin(checkout)

        checker.assert_awaited_once_with(checkout)
        creator.assert_not_awaited()

    async def test_no_fallback_when_coverage_exists(self, hass: HomeAssistant) -> None:
        """When turnover event exists, no fallback is created."""
        checker = AsyncMock(return_value=True)
        creator = AsyncMock()

        store = _make_mock_store(persisted_state=None)
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
            coverage_checker=checker,
            fallback_creator=creator,
        )
        await machine.async_initialize()

        checkout = datetime(2026, 3, 20, 11, 0, tzinfo=UTC)
        await machine.async_handle_checkin(checkout)

        creator.assert_not_awaited()

    async def test_fallback_created_when_no_coverage(self, hass: HomeAssistant) -> None:
        """When no turnover event exists, fallback is created."""
        checker = AsyncMock(return_value=False)
        creator = AsyncMock()

        store = _make_mock_store(persisted_state=None)
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
            coverage_checker=checker,
            fallback_creator=creator,
        )
        await machine.async_initialize()

        checkout = datetime(2026, 3, 20, 11, 0, tzinfo=UTC)
        await machine.async_handle_checkin(checkout)

        creator.assert_awaited_once_with(checkout)

    async def test_no_validation_without_delegates(self, hass: HomeAssistant) -> None:
        """Check-in without delegates skips validation."""
        store = _make_mock_store(persisted_state=None)
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()

        checkout = datetime(2026, 3, 20, 11, 0, tzinfo=UTC)
        # Should not raise
        await machine.async_handle_checkin(checkout)

        assert machine.phase == PHASE_OCCUPIED


# ---------------------------------------------------------------------------
# T023 - RC event listeners
# ---------------------------------------------------------------------------


class TestRCEventListeners:
    """Tests for RC check-in / check-out HA event handling."""

    async def test_checkin_event_triggers_handle_checkin(
        self, hass: HomeAssistant
    ) -> None:
        """RC check-in event triggers async_handle_checkin."""
        store = _make_mock_store(persisted_state=None)
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()

        checkout = datetime(2026, 3, 20, 11, 0, tzinfo=UTC)
        with patch.object(
            machine,
            "async_handle_checkin",
            new_callable=AsyncMock,
        ) as mock_checkin:
            entity_id = "calendar.rental_control"

            async def _handler(event: Any) -> None:  # noqa: ANN401
                """Simulate the RC check-in handler."""
                data = event.data or {}
                if data.get("entity_id") != entity_id:
                    return
                raw = data.get("checkout_time")
                if raw is None:
                    return
                dt = datetime.fromisoformat(raw) if isinstance(raw, str) else raw
                await machine.async_handle_checkin(dt)

            hass.bus.async_listen(EVENT_RC_CHECKIN, _handler)
            hass.bus.async_fire(
                EVENT_RC_CHECKIN,
                {
                    "entity_id": entity_id,
                    "checkout_time": checkout.isoformat(),
                },
            )
            await hass.async_block_till_done()

            mock_checkin.assert_awaited_once_with(checkout)

    async def test_checkout_event_triggers_handle_checkout(
        self, hass: HomeAssistant
    ) -> None:
        """RC check-out event triggers async_handle_checkout."""
        persisted = _make_dirty_state(phase=PHASE_OCCUPIED)
        store = _make_mock_store(persisted_state=persisted)
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()

        with patch.object(
            machine,
            "async_handle_checkout",
            new_callable=AsyncMock,
        ) as mock_checkout:
            entity_id = "calendar.rental_control"

            async def _handler(event: Any) -> None:  # noqa: ANN401
                """Simulate the RC check-out handler."""
                data = event.data or {}
                if data.get("entity_id") != entity_id:
                    return
                await machine.async_handle_checkout()

            hass.bus.async_listen(EVENT_RC_CHECKOUT, _handler)
            hass.bus.async_fire(
                EVENT_RC_CHECKOUT,
                {"entity_id": entity_id},
            )
            await hass.async_block_till_done()

            mock_checkout.assert_awaited_once()

    async def test_event_filtering_ignores_other_entity(
        self, hass: HomeAssistant
    ) -> None:
        """Events for a different entity are ignored."""
        store = _make_mock_store(persisted_state=None)
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()

        with patch.object(
            machine,
            "async_handle_checkin",
            new_callable=AsyncMock,
        ) as mock_checkin:
            target_entity = "calendar.rental_control"

            async def _handler(event: Any) -> None:  # noqa: ANN401
                """Simulate handler with entity filter."""
                data = event.data or {}
                if data.get("entity_id") != target_entity:
                    return
                raw = data.get("checkout_time")
                if raw and isinstance(raw, str):
                    dt = datetime.fromisoformat(raw)
                    await machine.async_handle_checkin(dt)

            hass.bus.async_listen(EVENT_RC_CHECKIN, _handler)

            # Fire event for a different entity
            hass.bus.async_fire(
                EVENT_RC_CHECKIN,
                {
                    "entity_id": "calendar.other_rental",
                    "checkout_time": (
                        datetime(
                            2026,
                            3,
                            20,
                            11,
                            0,
                            tzinfo=UTC,
                        ).isoformat()
                    ),
                },
            )
            await hass.async_block_till_done()

            mock_checkin.assert_not_awaited()


class TestAsyncReconcileActiveStay:
    """Tests for _async_reconcile_active_stay startup reconciliation."""

    @freeze_time("2026-06-10T14:00:00+00:00")
    async def test_active_stay_triggers_checkin(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Active guest stay at startup triggers async_handle_checkin."""
        now = datetime(2026, 6, 10, 14, 0, tzinfo=UTC)
        checkin = now - timedelta(hours=3)
        checkout = now + timedelta(hours=20)

        cal_event = MagicMock()
        cal_event.start = checkin
        cal_event.end = checkout

        calendar_entity = MagicMock()
        calendar_entity.async_get_events = AsyncMock(
            return_value=[cal_event],
        )

        coordinator = MagicMock()
        coordinator.calendar_entity = calendar_entity

        store = _make_mock_store(persisted_state=None)
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()

        with patch.object(
            machine,
            "async_handle_checkin",
            new_callable=AsyncMock,
        ) as mock_checkin:
            await _async_reconcile_active_stay(
                hass,
                coordinator,
                machine,
                "UTC",
            )
            mock_checkin.assert_awaited_once_with(checkout)

    @freeze_time("2026-06-10T14:00:00+00:00")
    async def test_no_active_stay_no_transition(
        self,
        hass: HomeAssistant,
    ) -> None:
        """No active guest stay at startup triggers no transition."""
        now = datetime(2026, 6, 10, 14, 0, tzinfo=UTC)

        past_event = MagicMock()
        past_event.start = now - timedelta(days=2)
        past_event.end = now - timedelta(days=1)

        future_event = MagicMock()
        future_event.start = now + timedelta(days=1)
        future_event.end = now + timedelta(days=3)

        calendar_entity = MagicMock()
        calendar_entity.async_get_events = AsyncMock(
            return_value=[past_event, future_event],
        )

        coordinator = MagicMock()
        coordinator.calendar_entity = calendar_entity

        store = _make_mock_store(persisted_state=None)
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()

        with patch.object(
            machine,
            "async_handle_checkin",
            new_callable=AsyncMock,
        ) as mock_checkin:
            await _async_reconcile_active_stay(
                hass,
                coordinator,
                machine,
                "UTC",
            )
            mock_checkin.assert_not_awaited()

    @freeze_time("2026-06-10T14:00:00+00:00")
    async def test_multiple_events_only_current_triggers(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Only the event spanning now triggers checkin."""
        now = datetime(2026, 6, 10, 14, 0, tzinfo=UTC)

        past_event = MagicMock()
        past_event.start = now - timedelta(days=5)
        past_event.end = now - timedelta(days=3)

        active_event = MagicMock()
        active_event.start = now - timedelta(hours=2)
        active_event.end = now + timedelta(hours=22)

        future_event = MagicMock()
        future_event.start = now + timedelta(days=2)
        future_event.end = now + timedelta(days=4)

        calendar_entity = MagicMock()
        calendar_entity.async_get_events = AsyncMock(
            return_value=[past_event, active_event, future_event],
        )

        coordinator = MagicMock()
        coordinator.calendar_entity = calendar_entity

        store = _make_mock_store(persisted_state=None)
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()

        with patch.object(
            machine,
            "async_handle_checkin",
            new_callable=AsyncMock,
        ) as mock_checkin:
            await _async_reconcile_active_stay(
                hass,
                coordinator,
                machine,
                "UTC",
            )
            mock_checkin.assert_awaited_once_with(active_event.end)


# ---------------------------------------------------------------------------
# T040 - Mid-stay cancellation
# ---------------------------------------------------------------------------


class TestAsyncHandleMidstayCancellation:
    """Tests for async_handle_midstay_cancellation."""

    @freeze_time("2026-03-15T14:00:00+00:00")
    async def test_clean_to_dirty_awaiting_cleaning(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Clean property becomes dirty with correct phase and reason."""
        store = _make_mock_store(persisted_state=None)
        fallback = AsyncMock()
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
            fallback_creator=fallback,
        )
        await machine.async_initialize()

        checkin = datetime(2026, 3, 14, 10, 0, tzinfo=UTC)
        await machine.async_handle_midstay_cancellation(checkin)

        assert machine.is_dirty is True
        assert machine.phase == PHASE_AWAITING_CLEANING
        assert machine.state.last_transition_reason == REASON_MID_STAY_CANCELLATION

    @freeze_time("2026-03-15T14:00:00+00:00")
    async def test_creates_immediate_cleaning_event(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Fallback creator called with current time."""
        store = _make_mock_store(persisted_state=None)
        fallback = AsyncMock()
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
            fallback_creator=fallback,
        )
        await machine.async_initialize()

        checkin = datetime(2026, 3, 14, 10, 0, tzinfo=UTC)
        await machine.async_handle_midstay_cancellation(checkin)

        now = datetime(2026, 3, 15, 14, 0, tzinfo=UTC)
        fallback.assert_awaited_once_with(now)

    @freeze_time("2026-03-15T14:00:00+00:00")
    async def test_already_dirty_stays_dirty_no_duplicate(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Already dirty property stays dirty, no duplicate event."""
        persisted = _make_dirty_state(phase=PHASE_AWAITING_CLEANING)
        store = _make_mock_store(persisted_state=persisted)
        fallback = AsyncMock()
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
            fallback_creator=fallback,
        )
        await machine.async_initialize()

        checkin = datetime(2026, 3, 14, 10, 0, tzinfo=UTC)
        await machine.async_handle_midstay_cancellation(checkin)

        assert machine.is_dirty is True
        fallback.assert_not_awaited()

    @freeze_time("2026-03-15T14:00:00+00:00")
    async def test_pre_arrival_cancellation_does_not_trigger(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Pre-arrival cancellation (check-in not yet passed) is no-op."""
        store = _make_mock_store(persisted_state=None)
        fallback = AsyncMock()
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
            fallback_creator=fallback,
        )
        await machine.async_initialize()

        future_checkin = datetime(2026, 3, 16, 10, 0, tzinfo=UTC)
        await machine.async_handle_midstay_cancellation(future_checkin)

        assert machine.is_dirty is False
        assert machine.phase == PHASE_CLEAN
        fallback.assert_not_awaited()

    @freeze_time("2026-03-15T14:00:00+00:00")
    async def test_persists_state(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Mid-stay cancellation persists the new state."""
        store = _make_mock_store(persisted_state=None)
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()
        store.schedule_save.reset_mock()

        checkin = datetime(2026, 3, 14, 10, 0, tzinfo=UTC)
        await machine.async_handle_midstay_cancellation(checkin)

        store.schedule_save.assert_called()

    @freeze_time("2026-03-15T14:00:00+00:00")
    async def test_fires_callbacks(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Mid-stay cancellation fires registered callbacks."""
        store = _make_mock_store(persisted_state=None)
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()

        callback = MagicMock()
        machine.register_callback(callback)

        checkin = datetime(2026, 3, 14, 10, 0, tzinfo=UTC)
        await machine.async_handle_midstay_cancellation(checkin)

        callback.assert_called_once()

    @freeze_time("2026-03-15T14:00:00+00:00")
    async def test_no_fallback_creator_still_transitions(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Without fallback_creator, state still transitions."""
        store = _make_mock_store(persisted_state=None)
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()

        checkin = datetime(2026, 3, 14, 10, 0, tzinfo=UTC)
        await machine.async_handle_midstay_cancellation(checkin)

        assert machine.is_dirty is True
        assert machine.phase == PHASE_AWAITING_CLEANING

    @freeze_time("2026-03-15T14:00:00+00:00")
    async def test_occupied_stays_dirty_no_duplicate(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Occupied property stays dirty, no duplicate event."""
        persisted = _make_dirty_state(phase=PHASE_OCCUPIED)
        store = _make_mock_store(persisted_state=persisted)
        fallback = AsyncMock()
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
            fallback_creator=fallback,
        )
        await machine.async_initialize()

        checkin = datetime(2026, 3, 14, 10, 0, tzinfo=UTC)
        await machine.async_handle_midstay_cancellation(checkin)

        assert machine.is_dirty is True
        fallback.assert_not_awaited()

    @freeze_time("2026-03-15T14:00:00+00:00")
    async def test_naive_datetime_raises_value_error(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Naive check-in time raises ValueError."""
        store = _make_mock_store(persisted_state=None)
        machine = CleanlinessStateMachine(
            hass=hass,
            entry_id=_TEST_ENTRY_ID,
            store=store,
            cleaning_duration_hours=3.0,
        )
        await machine.async_initialize()

        naive = datetime(2026, 3, 14, 10, 0)  # noqa: DTZ001
        with pytest.raises(ValueError, match="tz-aware"):
            await machine.async_handle_midstay_cancellation(naive)
