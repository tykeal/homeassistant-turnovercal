# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Tests for TurnoverCalCleanlinessSensor binary sensor entity."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.turnovercal.binary_sensor import (
    TurnoverCalCleanlinessSensor,
    async_setup_entry,
)
from custom_components.turnovercal.cleanliness import (
    CleanlinessState,
    CleanlinessStateMachine,
)
from custom_components.turnovercal.const import (
    DOMAIN,
    PHASE_AWAITING_CLEANING,
    PHASE_BEING_CLEANED,
    PHASE_CLEAN,
    PHASE_OCCUPIED,
    REASON_CLEANING_DURATION_ELAPSED,
    REASON_GUEST_CHECKIN,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

UTC = ZoneInfo("UTC")
_TEST_ENTRY_ID = "test_entry_sensor"


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
    dirty_since: datetime | None = None,
    timer_target: datetime | None = None,
) -> CleanlinessState:
    """Create a dirty CleanlinessState for testing."""
    ts = now or datetime(2026, 3, 15, 14, 0, tzinfo=UTC)
    return CleanlinessState(
        is_dirty=True,
        phase=phase,
        last_transition_at=ts,
        last_transition_reason=REASON_GUEST_CHECKIN,
        dirty_since=dirty_since or ts,
        timer_target=timer_target,
        config_entry_id=entry_id,
    )


def _make_mock_state_machine(
    *,
    state: CleanlinessState | None = None,
) -> MagicMock:
    """Create a mock CleanlinessStateMachine with the given state."""
    machine = MagicMock(spec=CleanlinessStateMachine)
    st = state or _make_clean_state()
    machine.state = st
    machine.is_dirty = st.is_dirty
    machine.phase = st.phase

    # register_callback returns an unregister callable
    machine.register_callback = MagicMock(return_value=MagicMock())
    machine.unregister_callback = MagicMock()
    return machine


class _StubEntry:
    """Minimal config entry stub for sensor tests."""

    def __init__(self, entry_id: str = _TEST_ENTRY_ID) -> None:
        """Initialise with a given entry ID."""
        self.entry_id = entry_id


# ---------------------------------------------------------------------------
# Entity attribute tests
# ---------------------------------------------------------------------------


class TestCleanlinessSensorAttributes:
    """Tests for TurnoverCalCleanlinessSensor entity attributes."""

    def test_unique_id(self) -> None:
        """Unique ID follows the {entry_id}_cleanliness pattern."""
        entry = _StubEntry("my-entry-42")
        machine = _make_mock_state_machine()
        sensor = TurnoverCalCleanlinessSensor(entry, machine)  # type: ignore[arg-type]

        assert sensor.unique_id == "my-entry-42_cleanliness"

    def test_device_class_is_problem(self) -> None:
        """Device class is PROBLEM."""
        entry = _StubEntry()
        machine = _make_mock_state_machine()
        sensor = TurnoverCalCleanlinessSensor(entry, machine)  # type: ignore[arg-type]

        assert sensor.device_class == BinarySensorDeviceClass.PROBLEM

    def test_translation_key_is_dirty(self) -> None:
        """Translation key is 'dirty'."""
        entry = _StubEntry()
        machine = _make_mock_state_machine()
        sensor = TurnoverCalCleanlinessSensor(entry, machine)  # type: ignore[arg-type]

        assert sensor.translation_key == "dirty"

    def test_has_entity_name(self) -> None:
        """Entity uses the has_entity_name pattern."""
        entry = _StubEntry()
        machine = _make_mock_state_machine()
        sensor = TurnoverCalCleanlinessSensor(entry, machine)  # type: ignore[arg-type]

        assert sensor.has_entity_name is True

    def test_device_info_identifiers(self) -> None:
        """Device info uses (DOMAIN, entry_id) identifiers."""
        entry = _StubEntry("my-entry-99")
        machine = _make_mock_state_machine()
        sensor = TurnoverCalCleanlinessSensor(entry, machine)  # type: ignore[arg-type]

        assert sensor.device_info is not None
        assert sensor.device_info["identifiers"] == {
            (DOMAIN, "my-entry-99"),
        }


# ---------------------------------------------------------------------------
# is_on / state tests
# ---------------------------------------------------------------------------


class TestCleanlinessSensorState:
    """Tests for is_on reflecting cleanliness state machine."""

    def test_is_on_when_dirty(self) -> None:
        """Sensor is 'on' (problem detected) when property is dirty."""
        dirty_state = _make_dirty_state()
        machine = _make_mock_state_machine(state=dirty_state)
        entry = _StubEntry()
        sensor = TurnoverCalCleanlinessSensor(entry, machine)  # type: ignore[arg-type]

        assert sensor.is_on is True

    def test_is_off_when_clean(self) -> None:
        """Sensor is 'off' (no problem) when property is clean."""
        clean_state = _make_clean_state()
        machine = _make_mock_state_machine(state=clean_state)
        entry = _StubEntry()
        sensor = TurnoverCalCleanlinessSensor(entry, machine)  # type: ignore[arg-type]

        assert sensor.is_on is False

    def test_is_on_for_occupied_phase(self) -> None:
        """Sensor is 'on' for occupied phase (dirty)."""
        state = _make_dirty_state(phase=PHASE_OCCUPIED)
        machine = _make_mock_state_machine(state=state)
        entry = _StubEntry()
        sensor = TurnoverCalCleanlinessSensor(entry, machine)  # type: ignore[arg-type]

        assert sensor.is_on is True

    def test_is_on_for_being_cleaned_phase(self) -> None:
        """Sensor is 'on' for being_cleaned phase (still dirty)."""
        state = _make_dirty_state(phase=PHASE_BEING_CLEANED)
        machine = _make_mock_state_machine(state=state)
        entry = _StubEntry()
        sensor = TurnoverCalCleanlinessSensor(entry, machine)  # type: ignore[arg-type]

        assert sensor.is_on is True


# ---------------------------------------------------------------------------
# Extra state attributes
# ---------------------------------------------------------------------------


class TestCleanlinessSensorExtraAttributes:
    """Tests for extra_state_attributes on the cleanliness sensor."""

    def test_clean_state_attributes(self) -> None:
        """Clean state exposes expected attribute values."""
        now = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
        state = _make_clean_state(now=now)
        machine = _make_mock_state_machine(state=state)
        entry = _StubEntry()
        sensor = TurnoverCalCleanlinessSensor(entry, machine)  # type: ignore[arg-type]

        attrs = sensor.extra_state_attributes
        assert attrs is not None
        assert attrs["phase"] == PHASE_CLEAN
        assert attrs["last_transition_at"] == now.isoformat()
        assert attrs["last_transition_reason"] == REASON_CLEANING_DURATION_ELAPSED
        assert attrs["dirty_since"] is None
        assert attrs["timer_target"] is None

    def test_dirty_state_attributes_with_dirty_since(self) -> None:
        """Dirty state includes dirty_since as ISO string."""
        now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
        dirty_since = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
        state = _make_dirty_state(now=now, dirty_since=dirty_since)
        machine = _make_mock_state_machine(state=state)
        entry = _StubEntry()
        sensor = TurnoverCalCleanlinessSensor(entry, machine)  # type: ignore[arg-type]

        attrs = sensor.extra_state_attributes
        assert attrs is not None
        assert attrs["dirty_since"] == dirty_since.isoformat()

    def test_being_cleaned_attributes_with_timer_target(self) -> None:
        """Being-cleaned state includes timer_target as ISO string."""
        now = datetime(2026, 6, 1, 14, 0, tzinfo=UTC)
        timer_target = datetime(2026, 6, 1, 17, 0, tzinfo=UTC)
        state = _make_dirty_state(
            phase=PHASE_BEING_CLEANED,
            now=now,
            timer_target=timer_target,
        )
        machine = _make_mock_state_machine(state=state)
        entry = _StubEntry()
        sensor = TurnoverCalCleanlinessSensor(entry, machine)  # type: ignore[arg-type]

        attrs = sensor.extra_state_attributes
        assert attrs is not None
        assert attrs["timer_target"] == timer_target.isoformat()
        assert attrs["phase"] == PHASE_BEING_CLEANED

    def test_all_attribute_keys_present(self) -> None:
        """All required extra attribute keys are always present."""
        machine = _make_mock_state_machine()
        entry = _StubEntry()
        sensor = TurnoverCalCleanlinessSensor(entry, machine)  # type: ignore[arg-type]

        attrs = sensor.extra_state_attributes
        assert attrs is not None
        expected_keys = {
            "phase",
            "last_transition_at",
            "last_transition_reason",
            "dirty_since",
            "timer_target",
        }
        assert set(attrs.keys()) == expected_keys


# ---------------------------------------------------------------------------
# Callback registration / state updates
# ---------------------------------------------------------------------------


class TestCleanlinessSensorCallbacks:
    """Tests for callback registration and state machine listener."""

    @pytest.mark.asyncio
    async def test_registers_callback_on_added_to_hass(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Sensor registers a callback with the state machine on add."""
        machine = _make_mock_state_machine()
        entry = _StubEntry()
        sensor = TurnoverCalCleanlinessSensor(entry, machine)  # type: ignore[arg-type]
        sensor.hass = hass

        # Mock the RestoreEntity.async_get_last_state to return None
        with patch.object(
            sensor,
            "async_get_last_state",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await sensor.async_added_to_hass()

        machine.register_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_unregisters_callback_on_remove(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Sensor unregisters callback when removed from HA."""
        unregister_fn = MagicMock()
        machine = _make_mock_state_machine()
        machine.register_callback.return_value = unregister_fn
        entry = _StubEntry()
        sensor = TurnoverCalCleanlinessSensor(entry, machine)  # type: ignore[arg-type]
        sensor.hass = hass

        # First add to hass so the unregister callable is stored
        with patch.object(
            sensor,
            "async_get_last_state",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await sensor.async_added_to_hass()

        await sensor.async_will_remove_from_hass()

        unregister_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_callback_is_async_write_ha_state(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Registered callback is the entity's async_write_ha_state."""
        machine = _make_mock_state_machine()
        entry = _StubEntry()
        sensor = TurnoverCalCleanlinessSensor(entry, machine)  # type: ignore[arg-type]
        sensor.hass = hass

        # Capture the callback that gets registered
        registered_callback = None

        def _capture_callback(cb: object) -> MagicMock:
            """Capture the callback argument for inspection."""
            nonlocal registered_callback
            registered_callback = cb
            return MagicMock()

        machine.register_callback.side_effect = _capture_callback

        with patch.object(
            sensor,
            "async_get_last_state",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await sensor.async_added_to_hass()

        assert registered_callback is not None
        # The callback should be the entity's async_write_ha_state method
        assert registered_callback == sensor.async_write_ha_state


# ---------------------------------------------------------------------------
# async_setup_entry platform function
# ---------------------------------------------------------------------------


class TestAsyncSetupEntry:
    """Tests for the async_setup_entry platform function."""

    @pytest.mark.asyncio
    async def test_creates_sensor_entity(
        self,
        hass: HomeAssistant,
    ) -> None:
        """async_setup_entry creates a TurnoverCalCleanlinessSensor."""
        machine = _make_mock_state_machine()
        entry = _StubEntry()

        hass.data[DOMAIN] = {
            entry.entry_id: {
                "cleanliness": machine,
            },
        }

        added_entities: list[object] = []

        def _capture_entities(entities: list[object]) -> None:
            """Collect entities passed to async_add_entities."""
            added_entities.extend(entities)

        await async_setup_entry(hass, entry, _capture_entities)  # type: ignore[arg-type]

        assert len(added_entities) == 1
        assert isinstance(added_entities[0], TurnoverCalCleanlinessSensor)

    @pytest.mark.asyncio
    async def test_setup_entry_entity_has_correct_entry_id(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Entity created by setup_entry uses the correct config entry ID."""
        machine = _make_mock_state_machine()
        entry = _StubEntry("specific-entry-77")

        hass.data[DOMAIN] = {
            entry.entry_id: {
                "cleanliness": machine,
            },
        }

        added_entities: list[object] = []

        def _capture_entities(entities: list[object]) -> None:
            """Collect entities passed to async_add_entities."""
            added_entities.extend(entities)

        await async_setup_entry(hass, entry, _capture_entities)  # type: ignore[arg-type]

        sensor = added_entities[0]
        assert isinstance(sensor, TurnoverCalCleanlinessSensor)
        assert sensor.unique_id == "specific-entry-77_cleanliness"


# ---------------------------------------------------------------------------
# Device grouping
# ---------------------------------------------------------------------------


class TestCleanlinessSensorDeviceGrouping:
    """Tests that sensor belongs to same device as other entities."""

    def test_device_identifiers_match_calendar_pattern(self) -> None:
        """Device identifiers match the (DOMAIN, entry_id) pattern used by calendar."""
        entry = _StubEntry("shared-device-entry")
        machine = _make_mock_state_machine()
        sensor = TurnoverCalCleanlinessSensor(entry, machine)  # type: ignore[arg-type]

        # This is the same pattern used by TurnoverCalCalendarEntity
        # and TurnoverCalFeedUrlSensor
        expected_identifiers = {(DOMAIN, "shared-device-entry")}
        assert sensor.device_info is not None
        assert sensor.device_info["identifiers"] == expected_identifiers
