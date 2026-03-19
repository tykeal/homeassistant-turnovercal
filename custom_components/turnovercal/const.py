# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Constants for the TurnoverCal integration."""

DOMAIN = "turnovercal"

# Configuration keys
CONF_CALENDAR_ENTITY = "calendar_entity_id"
CONF_LOCK_ENTITY = "lock_entity_id"
CONF_CLEANING_CODE_SLOT = "cleaning_code_slot"
CONF_RETENTION_WEEKS = "retention_weeks"
CONF_SUMMARY_PREFIX = "summary_prefix"
CONF_PROPERTY_NAME = "property_name"
CONF_TRAILING_DURATION_HOURS = "trailing_duration_hours"
CONF_EARLY_UNLOCK_GRACE_HOURS = "early_unlock_grace_hours"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_LOCK_MONITORING = "lock_monitoring"

# Defaults
DEFAULT_RETENTION_WEEKS = 6
DEFAULT_SUMMARY_PREFIX = "Turnover"
DEFAULT_TRAILING_DURATION_HOURS = 4
DEFAULT_EARLY_UNLOCK_GRACE_HOURS = 2
DEFAULT_UPDATE_INTERVAL = 5
DEFAULT_LOCK_MONITORING = False

# Integration domains
KEYMASTER_DOMAIN = "keymaster"

# Selector limits
DEFAULT_CLEANING_CODE_SLOT_MAX = 1024

# Events
EVENT_KEYMASTER = "keymaster_lock_state_changed"
