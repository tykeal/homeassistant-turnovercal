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
    CONF_EARLY_UNLOCK_GRACE_HOURS,
    CONF_LOCK_ENTITY,
    CONF_LOCK_MONITORING,
    CONF_PROPERTY_NAME,
    CONF_RETENTION_WEEKS,
    CONF_SUMMARY_PREFIX,
    CONF_TRAILING_DURATION_HOURS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_EARLY_UNLOCK_GRACE_HOURS,
    DEFAULT_LOCK_MONITORING,
    DEFAULT_RETENTION_WEEKS,
    DEFAULT_SUMMARY_PREFIX,
    DEFAULT_TRAILING_DURATION_HOURS,
    DEFAULT_UPDATE_INTERVAL,
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
                lock_entity = user_input.get(CONF_LOCK_ENTITY)
                if not lock_entity or not lock_entity.startswith("lock."):
                    errors[CONF_LOCK_ENTITY] = "invalid_lock_entity"
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
                    data[CONF_LOCK_ENTITY] = user_input[CONF_LOCK_ENTITY]
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
                vol.Optional(CONF_LOCK_ENTITY): str,
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
    """Handle TurnoverCal options flow."""

    def __init__(self) -> None:
        """Initialize options flow."""
        self._pending_options: dict[str, Any] = {}

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the initial options step.

        Presents a form with all configurable options. Validates
        numeric ranges and routes to token regeneration if requested.

        Args:
            user_input: User-submitted form data or None on first show.

        Returns:
            ConfigFlowResult with form or created entry.

        """
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = self._validate_options(user_input)
            if not errors:
                regen = user_input.pop("regenerate_token", False)
                if regen:
                    self._pending_options = user_input
                    return await self.async_step_confirm_regen()
                return self.async_create_entry(data=user_input)

        opts = self.config_entry.options
        defaults = user_input or opts
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_RETENTION_WEEKS,
                    default=defaults.get(
                        CONF_RETENTION_WEEKS,
                        DEFAULT_RETENTION_WEEKS,
                    ),
                ): int,
                vol.Required(
                    CONF_SUMMARY_PREFIX,
                    default=defaults.get(
                        CONF_SUMMARY_PREFIX,
                        DEFAULT_SUMMARY_PREFIX,
                    ),
                ): str,
                vol.Required(
                    CONF_PROPERTY_NAME,
                    default=defaults.get(CONF_PROPERTY_NAME, ""),
                ): str,
                vol.Required(
                    CONF_TRAILING_DURATION_HOURS,
                    default=defaults.get(
                        CONF_TRAILING_DURATION_HOURS,
                        DEFAULT_TRAILING_DURATION_HOURS,
                    ),
                ): int,
                vol.Required(
                    CONF_EARLY_UNLOCK_GRACE_HOURS,
                    default=defaults.get(
                        CONF_EARLY_UNLOCK_GRACE_HOURS,
                        DEFAULT_EARLY_UNLOCK_GRACE_HOURS,
                    ),
                ): int,
                vol.Required(
                    CONF_UPDATE_INTERVAL,
                    default=defaults.get(
                        CONF_UPDATE_INTERVAL,
                        DEFAULT_UPDATE_INTERVAL,
                    ),
                ): int,
                vol.Optional(
                    CONF_LOCK_MONITORING,
                    default=defaults.get(
                        CONF_LOCK_MONITORING,
                        DEFAULT_LOCK_MONITORING,
                    ),
                ): bool,
                vol.Optional(
                    CONF_LOCK_ENTITY,
                    default=defaults.get(CONF_LOCK_ENTITY, ""),
                ): str,
                vol.Optional(
                    CONF_CLEANING_CODE_SLOT,
                    default=defaults.get(CONF_CLEANING_CODE_SLOT, 0),
                ): int,
                vol.Optional("regenerate_token", default=False): bool,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_confirm_regen(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle token regeneration confirmation.

        Shows a confirmation form. On confirmation, generates a new
        feed token and updates both the config entry and cache.

        Args:
            user_input: User-submitted data or None on first show.

        Returns:
            ConfigFlowResult with form or created entry.

        """
        if user_input is None:
            return self.async_show_form(
                step_id="confirm_regen",
                data_schema=vol.Schema({}),
            )

        new_token = generate_token()

        domain_data = self.hass.data.get(DOMAIN)
        if domain_data is not None:
            entry_data = domain_data.get(
                self.config_entry.entry_id,
            )
            if entry_data is not None:
                entry_data["feed_token"] = new_token
                cache = entry_data.get("cache")
                if cache is not None:
                    await cache.async_set_feed_token(new_token)

        # Batch data + options into a single update to avoid
        # triggering the update listener twice.
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={
                **self.config_entry.data,
                "feed_token": new_token,
            },
            options=self._pending_options,
        )

        return self.async_create_entry(data=self._pending_options)

    @staticmethod
    def _validate_options(
        user_input: dict[str, Any],
    ) -> dict[str, str]:
        """Validate option ranges and return errors dict.

        Args:
            user_input: The submitted form data.

        Returns:
            Dictionary of field → error key (empty if valid).

        """
        errors: dict[str, str] = {}
        _max_retention = 52
        _max_trailing = 24
        _max_interval = 60
        _max_grace = 12

        def _is_int(val: object) -> bool:
            """Check if value is int but not bool."""
            return isinstance(val, int) and not isinstance(val, bool)

        retention = user_input.get(CONF_RETENTION_WEEKS, 0)
        if not _is_int(retention) or retention < 1 or retention > _max_retention:
            errors[CONF_RETENTION_WEEKS] = "invalid_range"

        trailing = user_input.get(CONF_TRAILING_DURATION_HOURS, 0)
        if not _is_int(trailing) or trailing < 1 or trailing > _max_trailing:
            errors[CONF_TRAILING_DURATION_HOURS] = "invalid_range"

        interval = user_input.get(CONF_UPDATE_INTERVAL, 0)
        if not _is_int(interval) or interval < 1 or interval > _max_interval:
            errors[CONF_UPDATE_INTERVAL] = "invalid_range"

        grace = user_input.get(
            CONF_EARLY_UNLOCK_GRACE_HOURS,
            DEFAULT_EARLY_UNLOCK_GRACE_HOURS,
        )
        if not _is_int(grace) or grace < 0 or grace > _max_grace:
            errors[CONF_EARLY_UNLOCK_GRACE_HOURS] = "invalid_range"

        lock_monitoring = bool(
            user_input.get(
                CONF_LOCK_MONITORING,
                DEFAULT_LOCK_MONITORING,
            ),
        )
        if lock_monitoring:
            lock_entity = user_input.get(CONF_LOCK_ENTITY, "")
            if not lock_entity or not lock_entity.startswith("lock."):
                errors[CONF_LOCK_ENTITY] = "invalid_lock_entity"
            slot = user_input.get(CONF_CLEANING_CODE_SLOT, 0)
            if not _is_int(slot) or slot < 1:
                errors[CONF_CLEANING_CODE_SLOT] = "invalid_slot"

        return errors
