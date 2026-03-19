# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Tests for TurnoverCal config flow setup step."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockModule,
    mock_integration,
)

from custom_components.turnovercal.const import (
    CONF_CALENDAR_ENTITY,
    CONF_CLEANING_CODE_SLOT,
    CONF_LOCK_MONITORING,
    DOMAIN,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_FAKE_TOKEN = "test-token-43chars-aaabbbccc111222333"  # noqa: S105
_FAKE_TOKEN_2 = "generated-token-value-43chars-abcdef"  # noqa: S105
_EXISTING_TOKEN = "existing-token"  # noqa: S105


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


# ---------------------------------------------------------------------------
# Config flow - lock monitoring option
# ---------------------------------------------------------------------------


class TestConfigFlowLockMonitoring:
    """Tests for lock monitoring option in config flow."""

    async def test_lock_monitoring_sets_flag(self, hass: HomeAssistant) -> None:
        """Config entry records lock_monitoring when lock enabled."""
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
                    CONF_LOCK_MONITORING: True,
                    CONF_CLEANING_CODE_SLOT: 4,
                },
            )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_LOCK_MONITORING] is True

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

    async def test_lock_monitoring_without_slot_rejected(
        self, hass: HomeAssistant
    ) -> None:
        """Lock monitoring without a code slot shows error."""
        _register_calendar(hass)

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
        assert result["errors"] is not None
        assert CONF_CLEANING_CODE_SLOT in result["errors"]

    async def test_lock_monitoring_negative_slot_rejected(
        self, hass: HomeAssistant
    ) -> None:
        """Lock monitoring with negative code slot shows error."""
        _register_calendar(hass)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_CALENDAR_ENTITY: ("calendar.rental_control_beach_house"),
                CONF_LOCK_MONITORING: True,
                CONF_CLEANING_CODE_SLOT: -1,
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] is not None
        assert result["errors"][CONF_CLEANING_CODE_SLOT] == "invalid_slot"


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
        """Non-calendar entity is rejected."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_CALENDAR_ENTITY: "sensor.not_a_calendar",
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] is not None
        assert CONF_CALENDAR_ENTITY in result["errors"]
