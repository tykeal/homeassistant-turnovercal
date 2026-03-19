# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Tests for TurnoverCal config flow setup step."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockModule,
    mock_integration,
)

from custom_components.turnovercal.const import (
    CONF_CALENDAR_ENTITY,
    CONF_CLEANING_CODE_SLOT,
    CONF_EARLY_UNLOCK_GRACE_HOURS,
    CONF_KEYMASTER_DEVICE,
    CONF_LOCK_MONITORING,
    CONF_PROPERTY_NAME,
    CONF_RETENTION_WEEKS,
    CONF_SUMMARY_PREFIX,
    CONF_TRAILING_DURATION_HOURS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_EARLY_UNLOCK_GRACE_HOURS,
    DEFAULT_RETENTION_WEEKS,
    DEFAULT_SUMMARY_PREFIX,
    DEFAULT_TRAILING_DURATION_HOURS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigFlowResult
    from homeassistant.core import HomeAssistant

_FAKE_TOKEN = "test-token-43chars-aaabbbccc111222333"  # noqa: S105
_FAKE_TOKEN_2 = "generated-token-value-43chars-abcdef"  # noqa: S105
_EXISTING_TOKEN = "existing-token"  # noqa: S105
_REGEN_TOKEN = "regenerated-token-value-43chars-xyz"  # noqa: S105


async def _noop_async_setup(
    *_args: Any,  # noqa: ANN401
    **_kwargs: Any,  # noqa: ANN401
) -> bool:
    """No-op async setup for mock integrations."""
    return True


@pytest.fixture(autouse=True)
def _enable_custom_integrations(
    enable_custom_integrations: None,  # noqa: ARG001
    hass: HomeAssistant,
) -> None:
    """Enable custom integration discovery and mock deps."""
    mock_integration(
        hass,
        MockModule(
            "rental_control",
            async_setup=_noop_async_setup,
            async_setup_entry=_noop_async_setup,
        ),
        built_in=False,
    )


def _register_calendar(
    hass: HomeAssistant,
    entity_id: str = "calendar.rental_control_beach_house",
    friendly_name: str = "Rental Control Beach House",
) -> None:
    """Register a calendar entity in the registry and set state."""
    registry = er.async_get(hass)
    object_id = entity_id.removeprefix("calendar.")
    registry.async_get_or_create(
        domain="calendar",
        platform="rental_control",
        unique_id=f"rc_{object_id}",
        suggested_object_id=object_id,
    )
    hass.states.async_set(
        entity_id,
        "off",
        {"friendly_name": friendly_name},
    )


def _register_keymaster(hass: HomeAssistant) -> MockConfigEntry:
    """Register a mock keymaster config entry.

    Args:
        hass: Home Assistant instance.

    Returns:
        The mock keymaster config entry.

    """
    mock_integration(
        hass,
        MockModule(
            "keymaster",
            async_setup=_noop_async_setup,
            async_setup_entry=_noop_async_setup,
        ),
        built_in=False,
    )
    entry = MockConfigEntry(
        domain="keymaster",
        data={
            "lockname": "front_door",
            "lock_entity_id": "lock.front_door",
        },
        title="Front Door Lock",
    )
    entry.add_to_hass(hass)
    return entry


def _register_keymaster_device(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> str:
    """Register a keymaster device and return its ID.

    Args:
        hass: Home Assistant instance.
        config_entry: The keymaster config entry.

    Returns:
        The device ID string.

    """
    device_reg = dr.async_get(hass)
    device = device_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={("keymaster", config_entry.entry_id)},
        name=config_entry.title,
    )
    return device.id


def _schema_keys(
    result: ConfigFlowResult,
) -> set[str]:
    """Extract schema key names from a flow result.

    Args:
        result: The flow result containing data_schema.

    Returns:
        Set of schema key name strings.

    """
    data_schema = result["data_schema"]
    assert data_schema is not None
    return {k.schema if hasattr(k, "schema") else k for k in data_schema.schema}


# ---------------------------------------------------------------------------
# Config flow - setup step
# ---------------------------------------------------------------------------


class TestConfigFlowSetup:
    """Tests for the config flow user setup step."""

    async def test_step_user_shows_form(self, hass: HomeAssistant) -> None:
        """User step shows a form with entity selector."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

    async def test_step_user_creates_entry(self, hass: HomeAssistant) -> None:
        """Valid input creates a config entry."""
        _register_calendar(hass)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM

        with patch(
            "custom_components.turnovercal.config_flow.generate_token",
            return_value=_FAKE_TOKEN,
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={
                    CONF_CALENDAR_ENTITY: ("calendar.rental_control_beach_house"),
                },
            )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["title"] == "Beach House"
        assert (
            result["data"][CONF_CALENDAR_ENTITY]
            == "calendar.rental_control_beach_house"
        )
        assert "feed_token" in result["data"]

    async def test_token_generated_on_setup(self, hass: HomeAssistant) -> None:
        """A feed token is generated during setup."""
        _register_calendar(hass)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )

        with patch(
            "custom_components.turnovercal.config_flow.generate_token",
            return_value=_FAKE_TOKEN_2,
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={
                    CONF_CALENDAR_ENTITY: ("calendar.rental_control_beach_house"),
                },
            )

        assert result["data"]["feed_token"] == _FAKE_TOKEN_2

    async def test_no_keymaster_hides_lock_toggle(self, hass: HomeAssistant) -> None:
        """Lock monitoring toggle hidden when keymaster not configured."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert CONF_LOCK_MONITORING not in _schema_keys(result)

    async def test_keymaster_shows_lock_toggle(self, hass: HomeAssistant) -> None:
        """Lock monitoring toggle shown when keymaster is configured."""
        _register_keymaster(hass)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert CONF_LOCK_MONITORING in _schema_keys(result)


# ---------------------------------------------------------------------------
# Config flow - lock monitoring option
# ---------------------------------------------------------------------------


class TestConfigFlowLockMonitoring:
    """Tests for lock monitoring option in config flow."""

    async def test_lock_monitoring_routes_to_lock_step(
        self, hass: HomeAssistant
    ) -> None:
        """Enabling lock monitoring routes to lock step."""
        _register_calendar(hass)
        _register_keymaster(hass)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_CALENDAR_ENTITY: ("calendar.rental_control_beach_house"),
                CONF_LOCK_MONITORING: True,
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "lock"

    async def test_lock_monitoring_sets_flag(self, hass: HomeAssistant) -> None:
        """Config entry records lock_monitoring when lock enabled."""
        _register_calendar(hass)
        km_entry = _register_keymaster(hass)
        device_id = _register_keymaster_device(hass, km_entry)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )

        with patch(
            "custom_components.turnovercal.config_flow.generate_token",
            return_value=_FAKE_TOKEN,
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={
                    CONF_CALENDAR_ENTITY: ("calendar.rental_control_beach_house"),
                    CONF_LOCK_MONITORING: True,
                },
            )

            assert result["type"] is FlowResultType.FORM
            assert result["step_id"] == "lock"

            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={
                    CONF_KEYMASTER_DEVICE: device_id,
                    CONF_CLEANING_CODE_SLOT: 4,
                },
            )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_LOCK_MONITORING] is True
        assert result["data"][CONF_KEYMASTER_DEVICE] == device_id
        assert result["data"][CONF_CLEANING_CODE_SLOT] == 4

    async def test_no_lock_monitoring_sets_false(self, hass: HomeAssistant) -> None:
        """Config entry records lock_monitoring=False when not set."""
        _register_calendar(hass)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )

        with patch(
            "custom_components.turnovercal.config_flow.generate_token",
            return_value=_FAKE_TOKEN,
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={
                    CONF_CALENDAR_ENTITY: ("calendar.rental_control_beach_house"),
                },
            )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_LOCK_MONITORING] is False

    async def test_lock_step_invalid_device_rejected(self, hass: HomeAssistant) -> None:
        """Lock step with non-existent device shows error."""
        _register_calendar(hass)
        _register_keymaster(hass)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_CALENDAR_ENTITY: ("calendar.rental_control_beach_house"),
                CONF_LOCK_MONITORING: True,
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "lock"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_KEYMASTER_DEVICE: "nonexistent-device-id",
                CONF_CLEANING_CODE_SLOT: 4,
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] is not None
        assert CONF_KEYMASTER_DEVICE in result["errors"]

    async def test_lock_step_negative_slot_rejected(self, hass: HomeAssistant) -> None:
        """Lock step with negative code slot is rejected by schema."""
        _register_calendar(hass)
        km_entry = _register_keymaster(hass)
        device_id = _register_keymaster_device(hass, km_entry)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_CALENDAR_ENTITY: ("calendar.rental_control_beach_house"),
                CONF_LOCK_MONITORING: True,
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "lock"

        with pytest.raises(InvalidData):
            await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={
                    CONF_KEYMASTER_DEVICE: device_id,
                    CONF_CLEANING_CODE_SLOT: -1,
                },
            )

    async def test_lock_step_float_slot_rejected(self, hass: HomeAssistant) -> None:
        """Lock step rejects non-integer float code slot."""
        _register_calendar(hass)
        km_entry = _register_keymaster(hass)
        device_id = _register_keymaster_device(hass, km_entry)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_CALENDAR_ENTITY: ("calendar.rental_control_beach_house"),
                CONF_LOCK_MONITORING: True,
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "lock"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_KEYMASTER_DEVICE: device_id,
                CONF_CLEANING_CODE_SLOT: 1.5,
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] is not None
        assert CONF_CLEANING_CODE_SLOT in result["errors"]

    async def test_lock_step_slot_over_max_rejected(self, hass: HomeAssistant) -> None:
        """Lock step rejects slot above maximum."""
        _register_calendar(hass)
        km_entry = _register_keymaster(hass)
        device_id = _register_keymaster_device(hass, km_entry)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_CALENDAR_ENTITY: "calendar.rental_control_beach_house",
                CONF_LOCK_MONITORING: True,
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "lock"

        with pytest.raises(InvalidData):
            await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={
                    CONF_KEYMASTER_DEVICE: device_id,
                    CONF_CLEANING_CODE_SLOT: 1025,
                },
            )


class TestConfigFlowValidation:
    """Tests for config flow validation."""

    async def test_duplicate_calendar_rejected(self, hass: HomeAssistant) -> None:
        """Same calendar entity cannot be configured twice."""
        _register_calendar(hass)

        existing = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_CALENDAR_ENTITY: ("calendar.rental_control_beach_house"),
                "feed_token": _EXISTING_TOKEN,
                CONF_LOCK_MONITORING: False,
            },
            unique_id="calendar.rental_control_beach_house",
        )
        existing.add_to_hass(hass)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )

        with patch(
            "custom_components.turnovercal.config_flow.generate_token",
            return_value=_FAKE_TOKEN,
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                user_input={
                    CONF_CALENDAR_ENTITY: ("calendar.rental_control_beach_house"),
                },
            )

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "already_configured"

    async def test_invalid_entity_rejected(self, hass: HomeAssistant) -> None:
        """Unregistered calendar entity is rejected."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_CALENDAR_ENTITY: "calendar.nonexistent",
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] is not None
        assert CONF_CALENDAR_ENTITY in result["errors"]


# ---------------------------------------------------------------------------
# Options flow
# ---------------------------------------------------------------------------


class TestOptionsFlow:
    """Tests for the TurnoverCal options flow."""

    @staticmethod
    def _create_entry(hass: HomeAssistant) -> MockConfigEntry:
        """Create and register a MockConfigEntry for options tests."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_CALENDAR_ENTITY: ("calendar.rental_control_beach_house"),
                "feed_token": _EXISTING_TOKEN,
                CONF_LOCK_MONITORING: False,
            },
            options={
                CONF_PROPERTY_NAME: "Beach House",
                CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            },
            unique_id="calendar.rental_control_beach_house",
        )
        entry.add_to_hass(hass)
        return entry

    async def test_options_flow_shows_form(self, hass: HomeAssistant) -> None:
        """Options flow shows form with all configurable fields."""
        entry = self._create_entry(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "init"
        keys = _schema_keys(result)
        assert CONF_RETENTION_WEEKS in keys
        assert CONF_SUMMARY_PREFIX in keys
        assert CONF_TRAILING_DURATION_HOURS in keys
        assert CONF_UPDATE_INTERVAL in keys
        assert CONF_PROPERTY_NAME in keys

    async def test_options_no_keymaster_hides_lock_toggle(
        self, hass: HomeAssistant
    ) -> None:
        """Lock toggle hidden in options when no keymaster."""
        entry = self._create_entry(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)

        assert CONF_LOCK_MONITORING not in _schema_keys(result)

    async def test_options_keymaster_shows_lock_toggle(
        self, hass: HomeAssistant
    ) -> None:
        """Lock toggle shown in options when keymaster configured."""
        _register_keymaster(hass)
        entry = self._create_entry(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)

        assert CONF_LOCK_MONITORING in _schema_keys(result)

    async def test_retention_weeks_changeable(self, hass: HomeAssistant) -> None:
        """Retention weeks can be changed from default to 12."""
        entry = self._create_entry(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: 12,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_PROPERTY_NAME: "Beach House",
            },
        )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_RETENTION_WEEKS] == 12

    async def test_retention_weeks_below_min_rejected(
        self, hass: HomeAssistant
    ) -> None:
        """Retention weeks of zero is rejected with error."""
        entry = self._create_entry(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: 0,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_PROPERTY_NAME: "Beach House",
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] is not None
        assert CONF_RETENTION_WEEKS in result["errors"]

    async def test_retention_weeks_above_max_rejected(
        self, hass: HomeAssistant
    ) -> None:
        """Retention weeks of 53 is rejected with error."""
        entry = self._create_entry(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: 53,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_PROPERTY_NAME: "Beach House",
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] is not None
        assert CONF_RETENTION_WEEKS in result["errors"]

    async def test_trailing_duration_below_min_rejected(
        self, hass: HomeAssistant
    ) -> None:
        """Trailing duration of zero is rejected with error."""
        entry = self._create_entry(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: 0,
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_PROPERTY_NAME: "Beach House",
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] is not None
        assert CONF_TRAILING_DURATION_HOURS in result["errors"]

    async def test_trailing_duration_above_max_rejected(
        self, hass: HomeAssistant
    ) -> None:
        """Trailing duration of 25 is rejected with error."""
        entry = self._create_entry(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: 25,
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_PROPERTY_NAME: "Beach House",
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] is not None
        assert CONF_TRAILING_DURATION_HOURS in result["errors"]

    async def test_update_interval_below_min_rejected(
        self, hass: HomeAssistant
    ) -> None:
        """Update interval of zero is rejected with error."""
        entry = self._create_entry(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                CONF_UPDATE_INTERVAL: 0,
                CONF_PROPERTY_NAME: "Beach House",
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] is not None
        assert CONF_UPDATE_INTERVAL in result["errors"]

    async def test_update_interval_above_max_rejected(
        self, hass: HomeAssistant
    ) -> None:
        """Update interval of 61 is rejected with error."""
        entry = self._create_entry(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                CONF_UPDATE_INTERVAL: 61,
                CONF_PROPERTY_NAME: "Beach House",
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] is not None
        assert CONF_UPDATE_INTERVAL in result["errors"]

    async def test_summary_prefix_changeable(self, hass: HomeAssistant) -> None:
        """Summary prefix can be changed and persists."""
        entry = self._create_entry(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                CONF_SUMMARY_PREFIX: "Cleaning",
                CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_PROPERTY_NAME: "Beach House",
            },
        )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_SUMMARY_PREFIX] == "Cleaning"

    async def test_trailing_duration_changeable(self, hass: HomeAssistant) -> None:
        """Trailing duration hours can be changed and persists."""
        entry = self._create_entry(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: 8,
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_PROPERTY_NAME: "Beach House",
            },
        )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_TRAILING_DURATION_HOURS] == 8

    async def test_update_interval_changeable(self, hass: HomeAssistant) -> None:
        """Update interval can be changed and persists."""
        entry = self._create_entry(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                CONF_UPDATE_INTERVAL: 15,
                CONF_PROPERTY_NAME: "Beach House",
            },
        )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_UPDATE_INTERVAL] == 15

    async def test_property_name_changeable(self, hass: HomeAssistant) -> None:
        """Property name can be changed and persists."""
        entry = self._create_entry(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_PROPERTY_NAME: "Mountain Cabin",
            },
        )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_PROPERTY_NAME] == "Mountain Cabin"

    async def test_token_regen_routes_to_confirm(self, hass: HomeAssistant) -> None:
        """Token regeneration routes to confirmation step."""
        entry = self._create_entry(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_PROPERTY_NAME: "Beach House",
                "regenerate_token": True,
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "confirm_regen"

    async def test_token_regen_updates_config_data(self, hass: HomeAssistant) -> None:
        """After regen confirmation, feed_token in data updates."""
        entry = self._create_entry(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)

        with patch(
            "custom_components.turnovercal.config_flow.generate_token",
            return_value=_REGEN_TOKEN,
        ):
            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                user_input={
                    CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                    CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                    CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                    CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                    CONF_PROPERTY_NAME: "Beach House",
                    "regenerate_token": True,
                },
            )

            assert result["type"] is FlowResultType.FORM
            assert result["step_id"] == "confirm_regen"

            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                user_input={},
            )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert entry.data["feed_token"] == _REGEN_TOKEN

    async def test_token_regen_updates_cache(self, hass: HomeAssistant) -> None:
        """After regen, CachedEventStore feed_token is updated."""
        entry = self._create_entry(hass)

        # Set up cache mock in hass.data
        hass.data.setdefault(DOMAIN, {})
        mock_cache = MagicMock()
        mock_cache.async_set_feed_token = AsyncMock()
        hass.data[DOMAIN][entry.entry_id] = {"cache": mock_cache}

        result = await hass.config_entries.options.async_init(entry.entry_id)

        with patch(
            "custom_components.turnovercal.config_flow.generate_token",
            return_value=_REGEN_TOKEN,
        ):
            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                user_input={
                    CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                    CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                    CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                    CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                    CONF_PROPERTY_NAME: "Beach House",
                    "regenerate_token": True,
                },
            )

            assert result["type"] is FlowResultType.FORM
            assert result["step_id"] == "confirm_regen"

            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                user_input={},
            )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        mock_cache.async_set_feed_token.assert_awaited_once_with(
            _REGEN_TOKEN,
        )
        assert hass.data[DOMAIN][entry.entry_id]["feed_token"] == _REGEN_TOKEN


# ---------------------------------------------------------------------------
# Options flow - lock settings
# ---------------------------------------------------------------------------


class TestOptionsFlowLockSettings:
    """Tests for lock settings in options flow."""

    @staticmethod
    def _create_entry_with_lock(
        hass: HomeAssistant,
    ) -> MockConfigEntry:
        """Create an entry with lock monitoring enabled."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_CALENDAR_ENTITY: ("calendar.rental_control_beach_house"),
                "feed_token": _EXISTING_TOKEN,
                CONF_LOCK_MONITORING: True,
                CONF_KEYMASTER_DEVICE: "fake-device-id",
                CONF_CLEANING_CODE_SLOT: 4,
            },
            options={
                CONF_PROPERTY_NAME: "Beach House",
                CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_LOCK_MONITORING: True,
                CONF_KEYMASTER_DEVICE: "fake-device-id",
                CONF_CLEANING_CODE_SLOT: 4,
                CONF_EARLY_UNLOCK_GRACE_HOURS: DEFAULT_EARLY_UNLOCK_GRACE_HOURS,
            },
            unique_id="calendar.rental_control_beach_house",
        )
        entry.add_to_hass(hass)
        return entry

    async def test_lock_monitoring_routes_to_lock_step(
        self, hass: HomeAssistant
    ) -> None:
        """Lock monitoring routes to lock step in options."""
        _register_keymaster(hass)
        entry = self._create_entry_with_lock(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_PROPERTY_NAME: "Beach House",
                CONF_LOCK_MONITORING: True,
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "lock"

    async def test_options_lock_step_shows_lock_fields(
        self, hass: HomeAssistant
    ) -> None:
        """Options lock step includes lock fields."""
        _register_keymaster(hass)
        entry = self._create_entry_with_lock(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_PROPERTY_NAME: "Beach House",
                CONF_LOCK_MONITORING: True,
            },
        )

        keys = _schema_keys(result)
        assert CONF_KEYMASTER_DEVICE in keys
        assert CONF_CLEANING_CODE_SLOT in keys
        assert CONF_EARLY_UNLOCK_GRACE_HOURS in keys

    async def test_lock_monitoring_toggle_off(self, hass: HomeAssistant) -> None:
        """Lock monitoring can be toggled off in options."""
        _register_keymaster(hass)
        entry = self._create_entry_with_lock(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_PROPERTY_NAME: "Beach House",
                CONF_LOCK_MONITORING: False,
            },
        )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_LOCK_MONITORING] is False

    async def test_cleaning_code_slot_changeable(self, hass: HomeAssistant) -> None:
        """Cleaning code slot can be changed in options."""
        km_entry = _register_keymaster(hass)
        device_id = _register_keymaster_device(hass, km_entry)
        entry = self._create_entry_with_lock(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_PROPERTY_NAME: "Beach House",
                CONF_LOCK_MONITORING: True,
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "lock"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_KEYMASTER_DEVICE: device_id,
                CONF_CLEANING_CODE_SLOT: 15,
                CONF_EARLY_UNLOCK_GRACE_HOURS: DEFAULT_EARLY_UNLOCK_GRACE_HOURS,
            },
        )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_CLEANING_CODE_SLOT] == 15

    async def test_grace_hours_changeable(self, hass: HomeAssistant) -> None:
        """Grace hours can be changed in lock step."""
        km_entry = _register_keymaster(hass)
        device_id = _register_keymaster_device(hass, km_entry)
        entry = self._create_entry_with_lock(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_PROPERTY_NAME: "Beach House",
                CONF_LOCK_MONITORING: True,
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "lock"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_KEYMASTER_DEVICE: device_id,
                CONF_CLEANING_CODE_SLOT: 4,
                CONF_EARLY_UNLOCK_GRACE_HOURS: 4,
            },
        )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_EARLY_UNLOCK_GRACE_HOURS] == 4

    async def test_grace_hours_below_min_rejected(self, hass: HomeAssistant) -> None:
        """Early unlock grace hours of -1 is rejected in lock step."""
        km_entry = _register_keymaster(hass)
        device_id = _register_keymaster_device(hass, km_entry)
        entry = self._create_entry_with_lock(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_PROPERTY_NAME: "Beach House",
                CONF_LOCK_MONITORING: True,
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "lock"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_KEYMASTER_DEVICE: device_id,
                CONF_CLEANING_CODE_SLOT: 4,
                CONF_EARLY_UNLOCK_GRACE_HOURS: -1,
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] is not None
        assert CONF_EARLY_UNLOCK_GRACE_HOURS in result["errors"]

    async def test_grace_hours_above_max_rejected(self, hass: HomeAssistant) -> None:
        """Early unlock grace hours of 13 is rejected in lock step."""
        km_entry = _register_keymaster(hass)
        device_id = _register_keymaster_device(hass, km_entry)
        entry = self._create_entry_with_lock(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_PROPERTY_NAME: "Beach House",
                CONF_LOCK_MONITORING: True,
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "lock"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_KEYMASTER_DEVICE: device_id,
                CONF_CLEANING_CODE_SLOT: 4,
                CONF_EARLY_UNLOCK_GRACE_HOURS: 13,
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] is not None
        assert CONF_EARLY_UNLOCK_GRACE_HOURS in result["errors"]

    async def test_lock_monitoring_requires_slot(self, hass: HomeAssistant) -> None:
        """Lock monitoring with zero code slot is rejected by schema."""
        km_entry = _register_keymaster(hass)
        device_id = _register_keymaster_device(hass, km_entry)
        entry = self._create_entry_with_lock(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_PROPERTY_NAME: "Beach House",
                CONF_LOCK_MONITORING: True,
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "lock"

        with pytest.raises(InvalidData):
            await hass.config_entries.options.async_configure(
                result["flow_id"],
                user_input={
                    CONF_KEYMASTER_DEVICE: device_id,
                    CONF_CLEANING_CODE_SLOT: 0,
                    CONF_EARLY_UNLOCK_GRACE_HOURS: DEFAULT_EARLY_UNLOCK_GRACE_HOURS,
                },
            )

    async def test_options_lock_step_float_slot_rejected(
        self, hass: HomeAssistant
    ) -> None:
        """Options lock step rejects non-integer float code slot."""
        km_entry = _register_keymaster(hass)
        device_id = _register_keymaster_device(hass, km_entry)
        entry = self._create_entry_with_lock(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_PROPERTY_NAME: "Beach House",
                CONF_LOCK_MONITORING: True,
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "lock"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_KEYMASTER_DEVICE: device_id,
                CONF_CLEANING_CODE_SLOT: 2.5,
                CONF_EARLY_UNLOCK_GRACE_HOURS: DEFAULT_EARLY_UNLOCK_GRACE_HOURS,
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] is not None
        assert CONF_CLEANING_CODE_SLOT in result["errors"]

    async def test_options_lock_step_slot_over_max_rejected(
        self, hass: HomeAssistant
    ) -> None:
        """Options lock step rejects slot above maximum."""
        km_entry = _register_keymaster(hass)
        device_id = _register_keymaster_device(hass, km_entry)
        entry = self._create_entry_with_lock(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_PROPERTY_NAME: "Beach House",
                CONF_LOCK_MONITORING: True,
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "lock"

        with pytest.raises(InvalidData):
            await hass.config_entries.options.async_configure(
                result["flow_id"],
                user_input={
                    CONF_KEYMASTER_DEVICE: device_id,
                    CONF_CLEANING_CODE_SLOT: 1025,
                    CONF_EARLY_UNLOCK_GRACE_HOURS: DEFAULT_EARLY_UNLOCK_GRACE_HOURS,
                },
            )

    async def test_keymaster_removed_forces_lock_off(self, hass: HomeAssistant) -> None:
        """Lock monitoring forced off when keymaster removed."""
        entry = self._create_entry_with_lock(hass)

        # No keymaster registered → forced off
        result = await hass.config_entries.options.async_init(entry.entry_id)

        # Lock toggle should not be in schema
        assert CONF_LOCK_MONITORING not in _schema_keys(result)

        # Submit without lock monitoring
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_PROPERTY_NAME: "Beach House",
            },
        )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_LOCK_MONITORING] is False

    async def test_lock_step_then_regen(self, hass: HomeAssistant) -> None:
        """Lock step followed by regen routes correctly."""
        km_entry = _register_keymaster(hass)
        device_id = _register_keymaster_device(hass, km_entry)
        entry = self._create_entry_with_lock(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)

        with patch(
            "custom_components.turnovercal.config_flow.generate_token",
            return_value=_REGEN_TOKEN,
        ):
            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                user_input={
                    CONF_RETENTION_WEEKS: DEFAULT_RETENTION_WEEKS,
                    CONF_SUMMARY_PREFIX: DEFAULT_SUMMARY_PREFIX,
                    CONF_TRAILING_DURATION_HOURS: DEFAULT_TRAILING_DURATION_HOURS,
                    CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                    CONF_PROPERTY_NAME: "Beach House",
                    CONF_LOCK_MONITORING: True,
                    "regenerate_token": True,
                },
            )

            assert result["type"] is FlowResultType.FORM
            assert result["step_id"] == "lock"

            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                user_input={
                    CONF_KEYMASTER_DEVICE: device_id,
                    CONF_CLEANING_CODE_SLOT: 4,
                    CONF_EARLY_UNLOCK_GRACE_HOURS: DEFAULT_EARLY_UNLOCK_GRACE_HOURS,
                },
            )

            assert result["type"] is FlowResultType.FORM
            assert result["step_id"] == "confirm_regen"

            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                user_input={},
            )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert entry.data["feed_token"] == _REGEN_TOKEN
