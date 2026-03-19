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
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    BooleanSelector,
    DeviceSelector,
    DeviceSelectorConfig,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
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
    DEFAULT_CLEANING_CODE_SLOT_MAX,
    DEFAULT_EARLY_UNLOCK_GRACE_HOURS,
    DEFAULT_LOCK_MONITORING,
    DEFAULT_RETENTION_WEEKS,
    DEFAULT_SUMMARY_PREFIX,
    DEFAULT_TRAILING_DURATION_HOURS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    KEYMASTER_DOMAIN,
)
from custom_components.turnovercal.token import generate_token

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigFlowResult
    from homeassistant.core import HomeAssistant


def _keymaster_available(hass: HomeAssistant) -> bool:
    """Check if keymaster integration is configured.

    Args:
        hass: Home Assistant instance.

    Returns:
        True if at least one keymaster config entry exists.

    """
    return len(hass.config_entries.async_entries(KEYMASTER_DOMAIN)) > 0


def _validate_keymaster_device(
    hass: HomeAssistant,
    device_id: str,
) -> str | None:
    """Validate a device is a keymaster lock with resolvable entity.

    Args:
        hass: Home Assistant instance.
        device_id: The device ID to validate.

    Returns:
        Error key string if invalid, None if valid.

    """
    device_reg = dr.async_get(hass)
    device = device_reg.async_get(device_id)
    if device is None:
        return "invalid_keymaster_device"

    for ce_id in device.config_entries:
        ce = hass.config_entries.async_get_entry(ce_id)
        lock_id = ce.data.get("lock_entity_id") if ce else None
        if (
            ce
            and ce.domain == KEYMASTER_DOMAIN
            and isinstance(lock_id, str)
            and lock_id.startswith("lock.")
        ):
            return None

    return "invalid_keymaster_device"


class TurnoverCalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for TurnoverCal."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        super().__init__()
        self._user_data: dict[str, Any] = {}

    def _validate_calendar(
        self,
        user_input: dict[str, Any],
    ) -> dict[str, str]:
        """Validate calendar entity input.

        Args:
            user_input: The submitted form data.

        Returns:
            Dictionary of field → error key (empty if valid).

        """
        errors: dict[str, str] = {}
        entity_id = user_input.get(CONF_CALENDAR_ENTITY, "")

        if not entity_id or not entity_id.startswith("calendar."):
            errors[CONF_CALENDAR_ENTITY] = "invalid_entity"
        else:
            registry = er.async_get(self.hass)
            entry = registry.async_get(entity_id)
            if entry is None:
                errors[CONF_CALENDAR_ENTITY] = "invalid_entity"

        return errors

    def _validate_lock(
        self,
        user_input: dict[str, Any],
    ) -> dict[str, str]:
        """Validate lock step input.

        Args:
            user_input: The submitted form data.

        Returns:
            Dictionary of field → error key (empty if valid).

        """
        errors: dict[str, str] = {}

        device_id = user_input.get(CONF_KEYMASTER_DEVICE)
        if not device_id:
            errors[CONF_KEYMASTER_DEVICE] = "invalid_keymaster_device"
        else:
            err = _validate_keymaster_device(self.hass, device_id)
            if err:
                errors[CONF_KEYMASTER_DEVICE] = err

        slot = user_input.get(CONF_CLEANING_CODE_SLOT)
        if slot is None:
            errors[CONF_CLEANING_CODE_SLOT] = "slot_required"
        elif isinstance(slot, bool):
            errors[CONF_CLEANING_CODE_SLOT] = "invalid_slot"
        elif isinstance(slot, int):
            if slot < 1 or slot > DEFAULT_CLEANING_CODE_SLOT_MAX:
                errors[CONF_CLEANING_CODE_SLOT] = "slot_out_of_range"
        elif isinstance(slot, float):
            if not slot.is_integer():
                errors[CONF_CLEANING_CODE_SLOT] = "invalid_slot"
            elif slot < 1 or slot > DEFAULT_CLEANING_CODE_SLOT_MAX:
                errors[CONF_CLEANING_CODE_SLOT] = "slot_out_of_range"
        else:
            errors[CONF_CLEANING_CODE_SLOT] = "invalid_slot"

        return errors

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the initial setup step.

        Presents a form for selecting the calendar entity and
        optionally enabling lock monitoring. Routes to the lock
        step when lock monitoring is enabled.

        Args:
            user_input: User-submitted form data or None on first show.

        Returns:
            ConfigFlowResult with form or created entry.

        """
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = self._validate_calendar(user_input)

            if not errors:
                entity_id = user_input[CONF_CALENDAR_ENTITY]
                await self.async_set_unique_id(entity_id)
                self._abort_if_unique_id_configured()

                lock_monitoring = bool(
                    user_input.get(
                        CONF_LOCK_MONITORING,
                        DEFAULT_LOCK_MONITORING,
                    ),
                )

                # Guard: force lock_monitoring off if keymaster absent
                if lock_monitoring and not _keymaster_available(self.hass):
                    lock_monitoring = False

                self._user_data = {
                    CONF_CALENDAR_ENTITY: entity_id,
                    CONF_LOCK_MONITORING: lock_monitoring,
                }

                if lock_monitoring:
                    return await self.async_step_lock()

                return self._create_entry()

        schema_dict: dict[vol.Marker, Any] = {
            vol.Required(CONF_CALENDAR_ENTITY): EntitySelector(
                EntitySelectorConfig(
                    domain="calendar",
                    integration="rental_control",
                ),
            ),
        }

        if _keymaster_available(self.hass):
            schema_dict[
                vol.Optional(
                    CONF_LOCK_MONITORING,
                    default=DEFAULT_LOCK_MONITORING,
                )
            ] = BooleanSelector()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    async def async_step_lock(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the lock configuration step.

        Presents a form for selecting the lock entity and
        cleaning code slot number when lock monitoring is enabled.

        Args:
            user_input: User-submitted form data or None on first show.

        Returns:
            ConfigFlowResult with form or created entry.

        """
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = self._validate_lock(user_input)

            if not errors:
                self._user_data[CONF_KEYMASTER_DEVICE] = user_input[
                    CONF_KEYMASTER_DEVICE
                ]
                self._user_data[CONF_CLEANING_CODE_SLOT] = int(
                    user_input[CONF_CLEANING_CODE_SLOT],
                )
                return self._create_entry()

        schema = vol.Schema(
            {
                vol.Required(CONF_KEYMASTER_DEVICE): DeviceSelector(
                    DeviceSelectorConfig(
                        integration=KEYMASTER_DOMAIN,
                    ),
                ),
                vol.Required(CONF_CLEANING_CODE_SLOT): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=DEFAULT_CLEANING_CODE_SLOT_MAX,
                        mode=NumberSelectorMode.BOX,
                        step=1,
                    ),
                ),
            },
        )

        return self.async_show_form(
            step_id="lock",
            data_schema=schema,
            errors=errors,
        )

    def _create_entry(self) -> ConfigFlowResult:
        """Create the config entry from collected data.

        Derives the property name from the entity friendly name,
        generates a feed token, and builds the data and options
        dictionaries for the config entry.

        Returns:
            ConfigFlowResult for the created entry.

        """
        entity_id = self._user_data[CONF_CALENDAR_ENTITY]
        lock_monitoring = self._user_data.get(
            CONF_LOCK_MONITORING,
            DEFAULT_LOCK_MONITORING,
        )

        friendly = entity_id
        state = self.hass.states.get(entity_id)
        if state is not None:
            friendly = state.attributes.get("friendly_name", entity_id)
        property_name = friendly.removeprefix("Rental Control ")

        token = generate_token()

        data: dict[str, Any] = {
            CONF_CALENDAR_ENTITY: entity_id,
            "feed_token": token,
            CONF_LOCK_MONITORING: lock_monitoring,
        }

        if lock_monitoring:
            data[CONF_KEYMASTER_DEVICE] = self._user_data[CONF_KEYMASTER_DEVICE]
            data[CONF_CLEANING_CODE_SLOT] = self._user_data[CONF_CLEANING_CODE_SLOT]

        options: dict[str, Any] = {
            CONF_PROPERTY_NAME: property_name,
        }

        return self.async_create_entry(
            title=property_name,
            data=data,
            options=options,
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
        self._regen_token: bool = False

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the initial options step.

        Presents a form with general configurable options. Routes
        to the lock step when lock monitoring is enabled, or to
        the token regeneration step if requested.

        Args:
            user_input: User-submitted form data or None on first show.

        Returns:
            ConfigFlowResult with form or created entry.

        """
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = self._validate_init_options(user_input)
            if not errors:
                self._regen_token = bool(
                    user_input.pop("regenerate_token", False),
                )

                keymaster = _keymaster_available(self.hass)
                lock_monitoring = bool(
                    user_input.pop(CONF_LOCK_MONITORING, False),
                )

                if not keymaster:
                    lock_monitoring = False

                self._pending_options = dict(user_input)
                self._pending_options[CONF_LOCK_MONITORING] = lock_monitoring

                if lock_monitoring:
                    return await self.async_step_lock()

                if self._regen_token:
                    return await self.async_step_confirm_regen()

                return self.async_create_entry(
                    data=self._pending_options,
                )

        opts = self.config_entry.options
        data = self.config_entry.data
        defaults = user_input or opts

        schema_dict: dict[vol.Marker, Any] = {
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
                CONF_UPDATE_INTERVAL,
                default=defaults.get(
                    CONF_UPDATE_INTERVAL,
                    DEFAULT_UPDATE_INTERVAL,
                ),
            ): int,
            vol.Optional("regenerate_token", default=False): bool,
        }

        if _keymaster_available(self.hass):
            current_lock = opts.get(
                CONF_LOCK_MONITORING,
                data.get(CONF_LOCK_MONITORING, DEFAULT_LOCK_MONITORING),
            )
            schema_dict[
                vol.Optional(
                    CONF_LOCK_MONITORING,
                    default=defaults.get(
                        CONF_LOCK_MONITORING,
                        current_lock,
                    ),
                )
            ] = BooleanSelector()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    async def async_step_lock(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle lock configuration options step.

        Presents a form for lock entity, cleaning code slot,
        and early unlock grace hours. Routes to token
        regeneration if requested, otherwise saves options.

        Args:
            user_input: User-submitted form data or None on first show.

        Returns:
            ConfigFlowResult with form or created entry.

        """
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = self._validate_lock_options(user_input)

            if not errors:
                self._pending_options[CONF_KEYMASTER_DEVICE] = user_input[
                    CONF_KEYMASTER_DEVICE
                ]
                self._pending_options[CONF_CLEANING_CODE_SLOT] = int(
                    user_input[CONF_CLEANING_CODE_SLOT],
                )
                self._pending_options[CONF_EARLY_UNLOCK_GRACE_HOURS] = int(
                    user_input[CONF_EARLY_UNLOCK_GRACE_HOURS],
                )

                if self._regen_token:
                    return await self.async_step_confirm_regen()

                return self.async_create_entry(
                    data=self._pending_options,
                )

        opts = self.config_entry.options
        data = self.config_entry.data

        device_default = opts.get(
            CONF_KEYMASTER_DEVICE,
            data.get(CONF_KEYMASTER_DEVICE, ""),
        )
        slot_default = opts.get(
            CONF_CLEANING_CODE_SLOT,
            data.get(CONF_CLEANING_CODE_SLOT, 1),
        )
        grace_default = opts.get(
            CONF_EARLY_UNLOCK_GRACE_HOURS,
            DEFAULT_EARLY_UNLOCK_GRACE_HOURS,
        )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_KEYMASTER_DEVICE,
                    default=device_default,
                ): DeviceSelector(
                    DeviceSelectorConfig(
                        integration=KEYMASTER_DOMAIN,
                    ),
                ),
                vol.Required(
                    CONF_CLEANING_CODE_SLOT,
                    default=slot_default,
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=DEFAULT_CLEANING_CODE_SLOT_MAX,
                        mode=NumberSelectorMode.BOX,
                        step=1,
                    ),
                ),
                vol.Required(
                    CONF_EARLY_UNLOCK_GRACE_HOURS,
                    default=grace_default,
                ): int,
            },
        )

        return self.async_show_form(
            step_id="lock",
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
    def _validate_init_options(
        user_input: dict[str, Any],
    ) -> dict[str, str]:
        """Validate init step option ranges.

        Args:
            user_input: The submitted form data.

        Returns:
            Dictionary of field → error key (empty if valid).

        """
        errors: dict[str, str] = {}
        _max_retention = 52
        _max_trailing = 24
        _max_interval = 60

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

        return errors

    def _validate_lock_options(
        self,
        user_input: dict[str, Any],
    ) -> dict[str, str]:
        """Validate lock step option values.

        Args:
            user_input: The submitted form data.

        Returns:
            Dictionary of field → error key (empty if valid).

        """
        errors: dict[str, str] = {}
        _max_grace = 12

        def _is_int(val: object) -> bool:
            """Check if value is int but not bool."""
            return isinstance(val, int) and not isinstance(val, bool)

        device_id = user_input.get(CONF_KEYMASTER_DEVICE, "")
        if not device_id:
            errors[CONF_KEYMASTER_DEVICE] = "invalid_keymaster_device"
        else:
            err = _validate_keymaster_device(self.hass, device_id)
            if err:
                errors[CONF_KEYMASTER_DEVICE] = err

        slot = user_input.get(CONF_CLEANING_CODE_SLOT, 0)
        if (
            isinstance(slot, bool)
            or not isinstance(slot, (int, float))
            or (isinstance(slot, float) and not slot.is_integer())
        ):
            errors[CONF_CLEANING_CODE_SLOT] = "invalid_slot"
        elif int(slot) < 1 or int(slot) > DEFAULT_CLEANING_CODE_SLOT_MAX:
            errors[CONF_CLEANING_CODE_SLOT] = "slot_out_of_range"

        grace = user_input.get(
            CONF_EARLY_UNLOCK_GRACE_HOURS,
            DEFAULT_EARLY_UNLOCK_GRACE_HOURS,
        )
        if not _is_int(grace) or grace < 0 or grace > _max_grace:
            errors[CONF_EARLY_UNLOCK_GRACE_HOURS] = "invalid_range"

        return errors
