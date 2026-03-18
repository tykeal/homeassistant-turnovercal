# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Config flow for TurnoverCal integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlow,
)
from homeassistant.helpers import entity_registry as er

from custom_components.turnovercal.const import (
    CONF_CALENDAR_ENTITY,
    CONF_CLEANING_CODE_SLOT,
    CONF_LOCK_MONITORING,
    CONF_PROPERTY_NAME,
    DEFAULT_LOCK_MONITORING,
    DOMAIN,
)
from custom_components.turnovercal.token import generate_token

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigFlowResult


class TurnoverCalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for TurnoverCal."""

    VERSION = 1

    def _validate_input(
        self,
        user_input: dict[str, Any],
    ) -> dict[str, str]:
        """Validate user input and return errors dict.

        Args:
            user_input: The submitted form data.

        Returns:
            Dictionary of field → error key (empty if valid).

        """
        errors: dict[str, str] = {}
        entity_id = user_input[CONF_CALENDAR_ENTITY]

        if not entity_id.startswith("calendar."):
            errors[CONF_CALENDAR_ENTITY] = "invalid_entity"
        else:
            registry = er.async_get(self.hass)
            entry = registry.async_get(entity_id)
            if entry is None:
                errors[CONF_CALENDAR_ENTITY] = "invalid_entity"

        if not errors:
            lock_monitoring = bool(
                user_input.get(
                    CONF_LOCK_MONITORING,
                    DEFAULT_LOCK_MONITORING,
                ),
            )
            if lock_monitoring:
                slot = user_input.get(CONF_CLEANING_CODE_SLOT)
                if slot is None:
                    errors[CONF_CLEANING_CODE_SLOT] = "slot_required"
                elif slot < 1:
                    errors[CONF_CLEANING_CODE_SLOT] = "invalid_slot"

        return errors

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the initial setup step.

        Presents a form for entering the calendar entity ID
        and optional lock monitoring settings. Generates a feed
        token and creates the config entry.

        Args:
            user_input: User-submitted form data or None on first show.

        Returns:
            ConfigFlowResult with form or created entry.

        """
        errors: dict[str, str] = {}

        if user_input is not None:
            entity_id = user_input[CONF_CALENDAR_ENTITY]
            errors = self._validate_input(user_input)

            if not errors:
                # Check for duplicate
                await self.async_set_unique_id(entity_id)
                self._abort_if_unique_id_configured()

                # Derive property name from entity friendly name
                friendly = entity_id
                state = self.hass.states.get(entity_id)
                if state is not None:
                    friendly = state.attributes.get("friendly_name", entity_id)
                property_name = friendly.removeprefix("Rental Control ")

                lock_monitoring = bool(
                    user_input.get(
                        CONF_LOCK_MONITORING,
                        DEFAULT_LOCK_MONITORING,
                    ),
                )

                token = generate_token()

                data: dict[str, Any] = {
                    CONF_CALENDAR_ENTITY: entity_id,
                    "feed_token": token,
                    CONF_LOCK_MONITORING: lock_monitoring,
                }

                if lock_monitoring:
                    data[CONF_CLEANING_CODE_SLOT] = user_input[CONF_CLEANING_CODE_SLOT]

                options: dict[str, Any] = {
                    CONF_PROPERTY_NAME: property_name,
                }

                return self.async_create_entry(
                    title=property_name,
                    data=data,
                    options=options,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_CALENDAR_ENTITY): str,
                vol.Optional(
                    CONF_LOCK_MONITORING,
                    default=DEFAULT_LOCK_MONITORING,
                ): bool,
                vol.Optional(CONF_CLEANING_CODE_SLOT): int,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        _config_entry: ConfigEntry,
    ) -> TurnoverCalOptionsFlow:
        """Return the options flow handler.

        Args:
            config_entry: The config entry to manage options for.

        Returns:
            The options flow handler instance.

        """
        return TurnoverCalOptionsFlow()


class TurnoverCalOptionsFlow(OptionsFlow):
    """Handle TurnoverCal options flow.

    Stub for Phase 4 (US2) implementation.
    """

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the initial options step.

        Args:
            user_input: User-submitted form data or None on first show.

        Returns:
            ConfigFlowResult with form or created entry.

        """
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),
        )
