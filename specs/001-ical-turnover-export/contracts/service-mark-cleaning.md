<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Contract: Manual Cleaning Signal Service

**Feature**: 001-ical-turnover-export
**Date**: 2026-03-17
**Type**: Home Assistant service call

## Service

```text
turnovercal.mark_cleaning_started
```

**Purpose**: Manual fallback to signal that cleaning has begun when
no Keymaster unlock event fires — either because no smart lock is
installed, the door was left open, or the lock integration failed.

**Behavior**: Applies the same turnover event adjustments as a
Keymaster `keymaster_lock_state_changed` unlock event:

- **During active turnover window**: Shortens DTEND per FR-009
  (00:00 day after call if next check-in is on a different day;
  unchanged if same day)
- **Within early-unlock grace period before checkout**: Moves
  DTSTART to the current time per FR-017
- **Outside both windows**: Logged as a warning; no adjustment

## Service Data Schema

```yaml
# services.yaml
mark_cleaning_started:
  name: Mark cleaning started
  description: >-
    Signal that cleaning has begun for a turnover window.
    Has the same effect as a Keymaster unlock event.
    Use when no smart lock is present or when the lock
    event failed to fire.
  target:
    entity:
      integration: turnovercal
      domain: calendar
  fields:
    timestamp:
      name: Timestamp
      description: >-
        Override timestamp for when cleaning started.
        Defaults to current time if not provided.
        Useful for retroactive adjustments.
      required: false
      example: "2026-03-10T09:30:00"
      selector:
        datetime:
```

## Request Examples

### Minimal (current time, entity target)

```yaml
service: turnovercal.mark_cleaning_started
target:
  entity_id: calendar.turnovercal_beach_house
```

### With explicit timestamp

```yaml
service: turnovercal.mark_cleaning_started
target:
  entity_id: calendar.turnovercal_beach_house
data:
  timestamp: "2026-03-10T09:30:00"
```

## Response

Services in Home Assistant do not return data. Outcomes are:

<!-- markdownlint-disable MD013 -->

| Condition | Result |
| --- | --- |
| Active turnover window exists | DTEND adjusted per FR-009; event cached; `adjustment_source` set to `"service_call"` |
| Within early-unlock grace period | DTSTART moved to signal time; event cached; `adjustment_source` set to `"service_call"` |
| No applicable turnover window | Warning logged; no change |
| Invalid entity target | Error raised (`ServiceValidationError`) |

<!-- markdownlint-enable MD013 -->

## Automation Examples

### Dashboard button

```yaml
type: button
name: "Cleaning Started"
tap_action:
  action: call-service
  service: turnovercal.mark_cleaning_started
  target:
    entity_id: calendar.turnovercal_beach_house
```

### NFC tag automation

```yaml
automation:
  trigger:
    - platform: tag
      tag_id: "cleaning-nfc-beach-house"
  action:
    - service: turnovercal.mark_cleaning_started
      target:
        entity_id: calendar.turnovercal_beach_house
```

### Motion sensor fallback (if no unlock detected)

```yaml
automation:
  trigger:
    - platform: state
      entity_id: binary_sensor.front_door_motion
      to: "on"
  condition:
    - condition: state
      entity_id: calendar.turnovercal_beach_house
      state: "on"
  action:
    - service: turnovercal.mark_cleaning_started
      target:
        entity_id: calendar.turnovercal_beach_house
```

## Idempotency

Multiple calls during the same turnover window are safe. Only the
first call adjusts the event; subsequent calls are no-ops (the
event is already in `adjusted` status). This prevents duplicate
adjustments from redundant automation triggers.
