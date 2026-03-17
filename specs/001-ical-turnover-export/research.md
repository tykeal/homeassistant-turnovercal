<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Research: TurnoverCal iCal Export

**Feature**: 001-ical-turnover-export
**Date**: 2026-03-16
**Status**: Complete

## R-001: Rental Control Integration Data Model

**Context**: TurnoverCal must read guest event data from Rental Control.
How does Rental Control expose this data?

**Decision**: Consume Rental Control's calendar entity via
`homeassistant.components.calendar` APIs.

**Rationale**: Rental Control creates a standard HA calendar entity
(`calendar.rental_control_<name>`) using `CalendarEntity`. Each guest
event is a `CalendarEvent` with `summary`, `start` (check-in datetime),
`end` (check-out datetime), `description`, and `location`. The
coordinator exposes events via `async_get_events(start_date, end_date)`.
Rental Control applies configurable check-in/check-out times to all-day
events (defaults: 16:00 check-in, 11:00 check-out). Each calendar
supports its own timezone via `ZoneInfo`.

**Alternatives considered**:

- *Direct ICS URL parsing*: Rejected — duplicates Rental Control's
  parsing logic and misses applied check-in/check-out time overrides.
- *Sensor entity attributes*: Rejected — sensors expose only the next
  N events (default 5) and lack the full event timeline needed for
  turnover calculation.
- *Rental Control coordinator direct access*: Rejected — tight
  coupling to internal API; calendar entity is the stable public
  interface.

**Key details**:

- Repository: `tykeal/homeassistant-rental-control`
- Dependencies: `icalendar>=6.1.0`, `x-wr-timezone>=2.0.0`
- Entity types: 1 calendar + N sensors per config entry
- Event age threshold: Events older than 30 days are discarded by
  Rental Control
- Future window: Configurable (default 365 days)

## R-002: Keymaster Lock Event Detection

**Context**: TurnoverCal must detect when cleaning staff unlock the
property during a turnover window (FR-008, FR-009). How does Keymaster
expose unlock events?

**Decision**: Listen for the `keymaster_lock_state_changed` event on
the HA event bus via `hass.bus.async_listen()`.  <!-- codespell:ignore hass -->

**Rationale**: Keymaster fires a single custom event type,
`keymaster_lock_state_changed`, on every lock/unlock action. The
event payload provides all the data needed to identify cleaning
staff unlocks during turnover windows:

```python
# Example keypad unlock event payload:
{
    "notification_source": "event",      # or "status_sync"
    "lockname": "Front Door",
    "entity_id": "lock.front_door",
    "state": "unlocked",                 # or "locked"
    "action_code": 6,                    # Z-Wave alarm code
    "action_text": "Keypad Unlock Code Slot 1",
    "code_slot_num": 1,                  # which code slot
    "code_slot_name": "John Doe",        # slot label
}
```

Key fields for TurnoverCal:

- `entity_id` — match against the Keymaster lock associated with the
  Rental Control calendar
- `state` — filter for `"unlocked"` only
- `code_slot_num` — correlate with Rental Control's managed code
  slots to identify which reservation triggered the unlock
- `code_slot_name` — additional context for logging/diagnostics

This event fires from `coordinator.py` in Keymaster via two methods:
`_lock_unlocked()` (includes `code_slot_num` and `code_slot_name`)
and `_lock_locked()` (omits code slot fields). Lock method is
determined by Z-Wave alarm codes mapped through `LockMethod` enum:
`MANUAL`, `KEYPAD`, `RF`, `AUTO`. Only `KEYPAD` events populate
`code_slot_num` with a non-zero value.

**Implementation pattern**:

<!-- markdownlint-disable MD013 -->

```python

EVENT_KEYMASTER = "keymaster_lock_state_changed"

@callback
def _handle_lock_event(event: Event) -> None:
    data = event.data
    # Filter: correct lock entity
    if data.get("entity_id") != configured_lock_entity_id:
        return
    # Filter: must be an unlock
    if data.get("state") != "unlocked":
        return
    # Filter: must be the configured cleaning staff slot
    code_slot = data.get("code_slot_num", 0)
    if code_slot != configured_cleaning_slot:
        return
    # This is a cleaning staff unlock — trigger adjustment
    _apply_cleaning_signal(now=dt_util.utcnow())

unsub = hass.bus.async_listen(EVENT_KEYMASTER, _handle_lock_event)  # codespell:ignore hass
entry.async_on_unload(unsub)
```

<!-- markdownlint-enable MD013 -->

The `code_slot_num` filter is the key discriminator. Cleaning staff
typically have a permanent, dedicated code slot in Keymaster (e.g.,
slot 15 is always the cleaning crew). Guest codes rotate through
other slots managed by Rental Control. By configuring which slot
number belongs to cleaning staff, TurnoverCal ignores all other
unlock activity (guests returning for forgotten items, maintenance,
manual unlocks, RF unlocks).

**Note**: Rental Control does NOT currently listen for this event.
TurnoverCal will be the first consumer of
`keymaster_lock_state_changed` outside of Keymaster itself.

**Alternatives considered**:

- *Monitor any unlock during turnover window*: Rejected — too
  broad; catches guests returning for forgotten items, maintenance
  workers, or any keypad/manual/RF unlock. Unacceptable false
  positive rate.
- *`async_track_state_change_event()` on lock entity*: Rejected —
  generic state changes lack `code_slot_num` and `action_text`
  detail. Would require inspecting lock entity attributes which may
  not be updated atomically with the state change.
- *HA event bus generic `state_changed` filter*: Rejected — higher
  noise; would receive every lock attribute change, not just
  meaningful lock/unlock actions. The Keymaster-specific event is
  pre-filtered and enriched with code slot data.
- *Polling lock state*: Rejected — introduces latency and unnecessary
  load; event-driven is real-time.

## R-003: iCal Feed HTTP Endpoint

**Context**: TurnoverCal must serve an iCal feed over HTTP without
interactive authentication (FR-003). How to implement this in HA?

**Decision**: Use `HomeAssistantView` with `requires_auth = False` and
a secret token embedded in the URL path.

**Rationale**: Home Assistant's `HomeAssistantView` (from
`homeassistant.helpers.http`) supports custom HTTP endpoints. Setting
`requires_auth = False` bypasses HA's auth middleware, allowing
calendar clients to access the feed without Bearer tokens. Security is
provided by a cryptographically random token in the URL path, validated
with `hmac.compare_digest()` to prevent timing attacks.

**Implementation pattern** (from Doorbird integration):

```python
class TurnoverCalView(HomeAssistantView):
    url = "/api/turnovercal/{token}/calendar.ics"
    name = "api:turnovercal:calendar"
    requires_auth = False

    async def get(self, request, token):
        if not hmac.compare_digest(token, stored_token):
            return web.Response(status=401)
        return web.Response(
            body=ical_bytes,
            content_type="text/calendar; charset=utf-8",
        )
```

**Alternatives considered**:

- *Query parameter token* (`?token=xxx`): Rejected — URL path tokens
  are more natural for calendar client subscription URLs and avoid
  query string stripping by some clients.
- *HA long-lived access token*: Rejected — requires auth headers that
  most calendar clients cannot provide in subscription URLs.
- *Webhook-based endpoint*: Considered but rejected — webhooks are
  designed for inbound data, not outbound feed serving.

**Security requirements**:

- Token generated via `secrets.token_urlsafe(32)` (FR-003)
- Token stored in config entry data (encrypted by HA)
- Token revocable/regenerable via options flow
- Token redacted from logs via HA's built-in sensitive data handling

## R-004: RFC 5545 iCal Generation

**Context**: The feed must conform to RFC 5545 (FR-004). Which Python
library and what generation patterns?

**Decision**: Use the `icalendar` library (v6.1.0+) for RFC 5545
compliant iCal generation.

**Rationale**: `icalendar` is the most actively maintained Python
iCalendar library (1,100+ stars, updated March 2026). It provides
full RFC 5545 compliance, automatic VTIMEZONE generation via
`cal.add_missing_timezones()`, and supports `zoneinfo.ZoneInfo` for
timezone handling (Python 3.9+ native). Rental Control already
depends on `icalendar>=6.1.0`, so no new transitive dependency is
introduced.

**Key implementation patterns**:

- **VCALENDAR**: PRODID, VERSION "2.0", CALSCALE "GREGORIAN",
  METHOD "PUBLISH"
- **VEVENT**: UID (SHA-256 hash), DTSTAMP (UTC), DTSTART/DTEND
  (local TZ with TZID), SUMMARY
- **VTIMEZONE**: Auto-generated via `cal.add_missing_timezones()`
- **UID generation**: `hashlib.sha256(source_id.encode()).hexdigest()
  [:16]@turnovercal.homeassistant` — one-way, deterministic, stable
  across recalculations (FR-010)
- **Zero-duration events**: DTEND = DTSTART + 1 minute (FR-011)
- **Content-Type**: `text/calendar; charset=utf-8`

**Alternatives considered**:

- *vobject*: Rejected — less maintained, heavier dependency tree.
- *ics.py*: Rejected — less mature timezone handling, fewer features
  for complex VTIMEZONE scenarios.
- *Manual string generation*: Rejected — error-prone for RFC 5545
  compliance (line folding, escaping, VTIMEZONE).

## R-005: Event Cache Persistence

**Context**: Turnover events must survive STR platform data removal
and HA restarts (FR-005). How to persist?

**Decision**: Use `homeassistant.helpers.storage.Store` for persistent
JSON storage with time-based expiry cleanup.

**Rationale**: `Store` is HA's standard mechanism for persistent JSON
data. It provides atomic writes, version migration, and delayed save
batching. Data is stored in `.storage/turnovercal_{entry_id}` and
survives HA restarts. Time-based cleanup runs via
`async_track_time_interval()` to remove events past the retention
period.

**Storage schema**:

```json
{
  "version": 1,
  "events": {
    "<uid>": {
      "uid": "abc123@turnovercal.homeassistant",
      "summary": "Turnover - Property Name",
      "dtstart": "2026-03-10T11:00:00",
      "dtend": "2026-03-10T15:00:00",
      "timezone": "America/New_York",
      "source_checkout_id": "...",
      "source_checkin_id": "...",
      "created_at": "2026-03-01T12:00:00Z",
      "status": "scheduled",
      "is_trailing": false,
      "adjusted_by_lock": false,
      "lock_unlock_time": null,
      "adjustment_source": null,
      "original_dtend": null,
      "original_dtstart": null
    }
  },
  "last_cleanup": "2026-03-16T00:00:00Z"
}
```

**Cleanup strategy**:

- Hourly `async_track_time_interval()` checks for expired events
- Events with `created_at` older than retention period are removed
- `store.async_delay_save(data, delay=5)` batches rapid updates

**Alternatives considered**:

- *SQLite database*: Rejected — overkill for the expected data volume
  (tens of events, not thousands); Store is simpler and standard.
- *HA Recorder*: Rejected — designed for entity state history, not
  arbitrary application data with custom expiry.
- *File-based cache*: Rejected — no atomic writes, no version
  migration, no HA integration.

## R-006: Config Flow Design

**Context**: TurnoverCal must be configurable through HA's standard
setup flow (FR-015). What config options are needed?

**Decision**: Two-step config flow (setup → options) with minimal
required fields.

**Rationale**: Following HA conventions, the config flow captures
required settings at setup time. Optional/tunable settings are exposed
via the options flow so users can adjust without reconfiguring.

**Setup flow (required)**:

1. Select Rental Control calendar entity (entity picker)
2. Auto-detect if Keymaster lock is associated with the selected
   calendar (from Rental Control's config)
3. If lock detected, ask whether to enable lock monitoring
4. If lock monitoring enabled, ask for the cleaning staff code
   slot number (integer input — this is the permanent Keymaster
   slot assigned to cleaning staff, e.g., slot 15)

**Options flow (adjustable)**:

- Retention period (default: 6 weeks, range: 1–52 weeks)
- Trailing turnover duration (default: 4 hours, range: 1–24 hours)
- Early-unlock grace period (default: 2 hours, range: 0–12 hours)
- Event summary prefix (default: "Turnover")
- URL path prefix (optional, does not replace token)
- Regenerate feed token (button)
- Lock monitoring toggle (if Keymaster available)
- Cleaning staff code slot (if lock monitoring enabled)

**Alternatives considered**:

- *YAML-only configuration*: Rejected — HA is moving away from YAML
  config for integrations; config flow is the standard.
- *Single-step flow with all options*: Rejected — overwhelming for
  initial setup; options flow allows progressive disclosure.

## R-007: Calendar Entity State Monitoring

**Context**: TurnoverCal needs to react to changes in Rental Control's
calendar. How to monitor for updates?

**Decision**: Use `async_track_state_change_event()` on the Rental
Control calendar entity and periodically query
`calendar.async_get_events()` via a `DataUpdateCoordinator`.

**Rationale**: The calendar entity's state changes to "on" when an
event is active and "off" otherwise. State change tracking catches
transitions. A `DataUpdateCoordinator` with a configurable update
interval (default: 5 minutes) periodically fetches the full event
list via the calendar platform's `async_get_events()` API to detect
new, modified, or removed events and recalculate turnover windows.

**Alternatives considered**:

- *State change events only*: Rejected — calendar state only indicates
  current event active/inactive; does not surface future event changes
  or modifications.
- *Direct Rental Control coordinator subscription*: Rejected — tight
  coupling; TurnoverCal should depend only on the public calendar
  entity API.

## R-008: Early Guest Departure Detection

**Context**: A guest may leave before the scheduled checkout time,
and cleaning staff may arrive and unlock the property early. The
turnover window has not technically started yet. How should
TurnoverCal handle this?

**Decision**: Honor Keymaster unlock events that occur within a
configurable grace period before the scheduled checkout time
(default: 2 hours). When honored, move the turnover event's DTSTART
to the unlock time, recognizing that cleaning has begun early.
Unlocks outside this grace period are ignored as before.

**Rationale**: A fixed grace period balances two concerns:

- Avoiding false positives from guest activity well before checkout
- Recognizing legitimate early departures when cleaners arrive
  shortly before the scheduled checkout

The 2-hour default matches common STR patterns where guests often
depart 1–2 hours before the formal checkout time. Setting the grace
period to 0 disables this feature entirely for users who prefer
strict window boundaries.

**Behavior**:

```text
Timeline for scheduled checkout at 11:00, grace period = 2 hours:

  08:00  08:30  09:00  09:30  10:00  10:30  11:00  ...
  |------|------|------|------|------|------|------|
  ▲ ignored                   ▲ grace window ▲ turnover starts
  (too early)                 (unlock honored,    (normal)
                               DTSTART moves)
```

- Unlock at 08:30 → ignored (outside 2-hour grace)
- Unlock at 09:15 → honored, DTSTART moves to 09:15
- Unlock at 10:30 → honored, DTSTART moves to 10:30
- Unlock at 11:30 → normal (already within turnover window)

**Alternatives considered**:

- *Ignore all pre-checkout unlocks*: Rejected — fails the common
  early-departure scenario; cleaning staff get no credit for extra
  time spent.
- *Honor all pre-checkout unlocks*: Rejected — high false-positive
  risk; guests unlocking hours before checkout would incorrectly
  trigger turnover start.
- *Move DTSTART to scheduled checkout but mark as "in progress"*:
  Rejected — loses information about when cleaning actually began;
  moving DTSTART is more useful for scheduling analysis.

## R-009: Manual Cleaning Signal Fallback

**Context**: Keymaster unlock events may not fire when the door was
left open by departing guests, no smart lock is installed, or the
lock integration fails. How should cleaning staff or automations
signal that cleaning has started?

**Decision**: Expose a Home Assistant service
(`turnovercal.mark_cleaning_started`) that applies the same
turnover adjustment logic as a Keymaster unlock event.

**Rationale**: An HA service call is the most composable mechanism
in the Home Assistant ecosystem. It can be triggered from:

- Dashboard buttons (Lovelace cards)
- NFC tags (scanned by cleaning staff on arrival)
- Automations (motion sensors, door contact sensors, etc.)
- Scripts and scenes
- Companion app quick actions
- Voice assistants (Alexa, Google)

The service shares the same internal adjustment handler as Keymaster
events (both call the same function), ensuring consistent behavior
regardless of trigger source. The `adjustment_source` field on the
event distinguishes Keymaster-triggered vs. manually-triggered
adjustments for auditing.

The service is idempotent — multiple calls during the same window
are safe; only the first call adjusts the event.

**Alternatives considered**:

- *Companion app notification with action buttons*: Rejected —
  requires additional integration and couples to the HA mobile app;
  a service call is more universal and can be wrapped in any UI.
- *Input boolean entity (toggle)*: Rejected — stateful toggles are
  harder to manage; a stateless service call with timestamp is
  cleaner and avoids "forgot to toggle off" issues.
- *MQTT trigger*: Rejected — adds external dependency; HA service
  calls are native and require no additional infrastructure.
