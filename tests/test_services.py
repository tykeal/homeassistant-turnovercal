# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Tests for the TurnoverCal service handlers."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
import yaml
from homeassistant.core import ServiceCall
from homeassistant.exceptions import ServiceValidationError

from custom_components.turnovercal.const import DOMAIN
from custom_components.turnovercal.models import TurnoverEvent
from custom_components.turnovercal.services import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_TIMESTAMP,
    _handle_mark_cleaning,
    _resolve_coordinators,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

# UID matching ^[0-9a-f]{16}@turnovercal\.homeassistant$
_TEST_UID = "a1b2c3d4e5f6a7b8@turnovercal.homeassistant"
_ENTRY_ID = "test_entry_123"


def _make_coordinator(
    entity_id: str = "calendar.rental_control_beach_house",
) -> MagicMock:
    """Create a mock TurnoverCoordinator."""
    coord = MagicMock()
    coord.calendar_entity_id = entity_id
    coord.apply_cleaning_signal = AsyncMock(return_value=True)
    coord.cache_events = {}
    coord.async_set_updated_data = MagicMock()
    return coord


def _make_service_call(
    hass: HomeAssistant,
    *,
    target: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
) -> ServiceCall:
    """Build a ServiceCall with target merged into data."""
    merged: dict[str, Any] = dict(data or {})
    if target and "entity_id" in target:
        merged["entity_id"] = target["entity_id"]
    call = MagicMock(spec=ServiceCall)
    call.hass = hass
    call.data = merged
    return call


def _make_event(
    uid: str = _TEST_UID,
    hours_from_now: int = 0,
    duration_hours: int = 4,
) -> TurnoverEvent:
    """Build a test TurnoverEvent."""
    base = datetime(2026, 3, 15, 10, 0, tzinfo=ET)
    return TurnoverEvent(
        uid=uid,
        summary="Turnover: Beach House",
        dtstart=base + timedelta(hours=hours_from_now),
        dtend=base
        + timedelta(
            hours=hours_from_now + duration_hours,
        ),
        timezone="America/New_York",
        source_checkout_id="checkout1",
        source_checkin_id="checkin1",
        created_at=datetime.now(tz=UTC),
    )


# -------------------------------------------------------------------
# T041: Service handler unit tests
# -------------------------------------------------------------------


class TestResolveCoordinator:
    """Tests for _resolve_coordinators targeting logic."""

    def test_entity_target_resolves(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Entity target resolves to correct coordinator."""
        coord = _make_coordinator()
        hass.data[DOMAIN] = {_ENTRY_ID: {"coordinator": coord}}
        call = _make_service_call(
            hass,
            target={
                "entity_id": ("calendar.rental_control_beach_house"),
            },
        )
        result = _resolve_coordinators(hass, call)
        assert result == [coord]

    def test_config_entry_id_resolves(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Config entry ID resolves to correct coordinator."""
        coord = _make_coordinator()
        hass.data[DOMAIN] = {_ENTRY_ID: {"coordinator": coord}}
        call = _make_service_call(
            hass,
            data={ATTR_CONFIG_ENTRY_ID: _ENTRY_ID},
        )
        result = _resolve_coordinators(hass, call)
        assert result == [coord]

    def test_both_targets_raises(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Both entity and config_entry_id raises error."""
        hass.data[DOMAIN] = {}
        call = _make_service_call(
            hass,
            target={
                "entity_id": ("calendar.rental_control_beach_house"),
            },
            data={ATTR_CONFIG_ENTRY_ID: _ENTRY_ID},
        )
        with pytest.raises(ServiceValidationError):
            _resolve_coordinators(hass, call)

    def test_neither_target_raises(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Neither entity nor config_entry_id raises error."""
        hass.data[DOMAIN] = {}
        call = _make_service_call(hass)
        with pytest.raises(ServiceValidationError):
            _resolve_coordinators(hass, call)

    def test_invalid_config_entry_raises(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Invalid config entry ID raises error."""
        hass.data[DOMAIN] = {}
        call = _make_service_call(
            hass,
            data={ATTR_CONFIG_ENTRY_ID: "nonexistent"},
        )
        with pytest.raises(ServiceValidationError):
            _resolve_coordinators(hass, call)

    def test_invalid_entity_raises(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Invalid entity target raises error."""
        hass.data[DOMAIN] = {_ENTRY_ID: {"coordinator": _make_coordinator()}}
        call = _make_service_call(
            hass,
            target={
                "entity_id": "calendar.nonexistent",
            },
        )
        with pytest.raises(ServiceValidationError):
            _resolve_coordinators(hass, call)


class TestHandleMarkCleaning:
    """Tests for the mark_cleaning_started handler."""

    async def test_calls_apply_cleaning_signal(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Service call triggers apply_cleaning_signal."""
        coord = _make_coordinator()
        hass.data[DOMAIN] = {_ENTRY_ID: {"coordinator": coord}}
        call = _make_service_call(
            hass,
            data={ATTR_CONFIG_ENTRY_ID: _ENTRY_ID},
        )
        await _handle_mark_cleaning(call)
        coord.apply_cleaning_signal.assert_awaited_once()
        args = coord.apply_cleaning_signal.call_args
        assert args.kwargs.get("source") == "service_call"

    async def test_timestamp_override(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Timestamp override is interpreted in HA timezone."""
        coord = _make_coordinator()
        hass.data[DOMAIN] = {_ENTRY_ID: {"coordinator": coord}}
        hass.config.time_zone = "America/New_York"
        call = _make_service_call(
            hass,
            data={
                ATTR_CONFIG_ENTRY_ID: _ENTRY_ID,
                ATTR_TIMESTAMP: "2026-03-15T10:30:00",
            },
        )
        await _handle_mark_cleaning(call)
        coord.apply_cleaning_signal.assert_awaited_once()
        now_arg = coord.apply_cleaning_signal.call_args[0][0]
        # Should be UTC: 10:30 ET = 14:30 UTC (EDT)
        assert now_arg.tzinfo == UTC
        assert now_arg.hour == 14
        assert now_arg.minute == 30

    async def test_datetime_timestamp_override(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Datetime object timestamp override works."""
        coord = _make_coordinator()
        hass.data[DOMAIN] = {_ENTRY_ID: {"coordinator": coord}}
        hass.config.time_zone = "America/New_York"
        ts = datetime(2026, 3, 15, 10, 30, 0)  # noqa: DTZ001
        call = _make_service_call(
            hass,
            data={
                ATTR_CONFIG_ENTRY_ID: _ENTRY_ID,
                ATTR_TIMESTAMP: ts,
            },
        )
        await _handle_mark_cleaning(call)
        now_arg = coord.apply_cleaning_signal.call_args[0][0]
        assert now_arg.hour == 14

    async def test_default_timestamp_is_now(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Default timestamp is current UTC time."""
        coord = _make_coordinator()
        hass.data[DOMAIN] = {_ENTRY_ID: {"coordinator": coord}}
        call = _make_service_call(
            hass,
            data={ATTR_CONFIG_ENTRY_ID: _ENTRY_ID},
        )
        before = datetime.now(tz=UTC)
        await _handle_mark_cleaning(call)
        after = datetime.now(tz=UTC)
        now_arg = coord.apply_cleaning_signal.call_args[0][0]
        assert before <= now_arg <= after

    async def test_aware_timestamp_preserved(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Aware datetime is converted without reinterpretation."""
        coord = _make_coordinator()
        hass.data[DOMAIN] = {_ENTRY_ID: {"coordinator": coord}}
        hass.config.time_zone = "America/New_York"
        # 10:30 PST = 18:30 UTC
        pst = ZoneInfo("America/Los_Angeles")
        ts = datetime(2026, 3, 15, 10, 30, 0, tzinfo=pst)
        call = _make_service_call(
            hass,
            data={
                ATTR_CONFIG_ENTRY_ID: _ENTRY_ID,
                ATTR_TIMESTAMP: ts,
            },
        )
        await _handle_mark_cleaning(call)
        now_arg = coord.apply_cleaning_signal.call_args[0][0]
        assert now_arg.tzinfo == UTC
        assert now_arg.hour == 17
        assert now_arg.minute == 30

    async def test_no_adjustment_logs_warning(
        self,
        hass: HomeAssistant,
    ) -> None:
        """No active window logs a warning."""
        coord = _make_coordinator()
        coord.apply_cleaning_signal = AsyncMock(
            return_value=False,
        )
        hass.data[DOMAIN] = {_ENTRY_ID: {"coordinator": coord}}
        call = _make_service_call(
            hass,
            data={ATTR_CONFIG_ENTRY_ID: _ENTRY_ID},
        )
        with patch(
            "custom_components.turnovercal.services._LOGGER",
        ) as mock_log:
            await _handle_mark_cleaning(call)
            mock_log.warning.assert_called_once()

    async def test_adjustment_updates_coordinator_data(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Successful adjustment notifies subscribers."""
        coord = _make_coordinator()
        hass.data[DOMAIN] = {_ENTRY_ID: {"coordinator": coord}}
        call = _make_service_call(
            hass,
            data={ATTR_CONFIG_ENTRY_ID: _ENTRY_ID},
        )
        await _handle_mark_cleaning(call)
        coord.async_set_updated_data.assert_called_once()

    async def test_idempotent_second_call(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Second call is no-op when already adjusted."""
        coord = _make_coordinator()
        coord.apply_cleaning_signal = AsyncMock(
            side_effect=[True, False],
        )
        hass.data[DOMAIN] = {_ENTRY_ID: {"coordinator": coord}}
        call = _make_service_call(
            hass,
            data={ATTR_CONFIG_ENTRY_ID: _ENTRY_ID},
        )
        await _handle_mark_cleaning(call)
        await _handle_mark_cleaning(call)
        assert coord.apply_cleaning_signal.await_count == 2
        # Only first call triggers data update
        coord.async_set_updated_data.assert_called_once()


# -------------------------------------------------------------------
# T042: Contract tests
# -------------------------------------------------------------------


class TestServiceContract:
    """Verify service matches contract specification."""

    _svc_path = Path(
        "custom_components/turnovercal/services.yaml",
    )

    def _load_yaml(self) -> dict[str, Any]:
        """Load the services.yaml file."""
        with self._svc_path.open() as f:
            result: dict[str, Any] = yaml.safe_load(f)
            return result

    def test_service_yaml_exists(self) -> None:
        """Service YAML file exists and is loadable."""
        data = self._load_yaml()
        assert "mark_cleaning_started" in data

    def test_service_schema_target(self) -> None:
        """Target matches contract: entity integration."""
        svc = self._load_yaml()["mark_cleaning_started"]
        target = svc["target"]
        assert target["entity"]["integration"] == "turnovercal"
        assert target["entity"]["domain"] == "calendar"

    def test_service_schema_fields(self) -> None:
        """Fields match contract specification."""
        fields = self._load_yaml()["mark_cleaning_started"]["fields"]

        assert "config_entry_id" in fields
        entry_field = fields["config_entry_id"]
        assert entry_field["required"] is False
        assert "config_entry" in entry_field["selector"]

        assert "timestamp" in fields
        ts_field = fields["timestamp"]
        assert ts_field["required"] is False
        assert "datetime" in ts_field["selector"]

    def test_service_name_and_description(self) -> None:
        """Name and description present."""
        svc = self._load_yaml()["mark_cleaning_started"]
        assert svc["name"] == "Mark cleaning started"
        assert len(svc["description"]) > 0
