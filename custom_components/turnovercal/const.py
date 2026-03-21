# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Constants for the TurnoverCal integration."""

DOMAIN = "turnovercal"

# Configuration keys
CONF_CALENDAR_ENTITY = "calendar_entity_id"
CONF_KEYMASTER_DEVICE = "keymaster_device_id"
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

# Keymaster config entry data keys
KM_LOCK_ENTITY_KEY = "lock_entity_id"

# Selector limits
DEFAULT_CLEANING_CODE_SLOT_MAX = 1024

# Events
EVENT_KEYMASTER = "keymaster_lock_state_changed"
EVENT_RC_CHECKIN = "rental_control_check_in"
EVENT_RC_CHECKOUT = "rental_control_check_out"

# Feed URL pattern (shared between HTTP view and sensor)
FEED_URL_PATH = "/api/turnovercal/{token}/calendar.ics"

# Cleanliness configuration
CONF_CLEANING_DURATION_HOURS = "cleaning_duration_hours"

# Cleanliness defaults
DEFAULT_CLEANING_DURATION_HOURS = 3
MIN_CLEANING_DURATION_HOURS = 0.05

# Cleanliness phase values
PHASE_CLEAN = "clean"
PHASE_OCCUPIED = "occupied"
PHASE_AWAITING_CLEANING = "awaiting_cleaning"
PHASE_BEING_CLEANED = "being_cleaned"

# Transition reason constants
REASON_GUEST_CHECKIN = "guest_checkin"
REASON_GUEST_CHECKOUT = "guest_checkout"
REASON_MID_STAY_CANCELLATION = "mid_stay_cancellation"
REASON_LOCK_CODE_ENTRY = "lock_code_entry"
REASON_CLEANING_DURATION_ELAPSED = "cleaning_duration_elapsed"
REASON_SERVICE_CALL_MARK_CLEAN = "service_call_mark_clean"
REASON_SERVICE_CALL_MARK_DIRTY = "service_call_mark_dirty"
REASON_STARTUP_RECONCILIATION = "startup_reconciliation"

# Cleanliness store
CLEANLINESS_STORE_VERSION = 1
