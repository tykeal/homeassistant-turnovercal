<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Feature Specification: TurnoverCal iCal Export

**Feature Branch**: `001-ical-turnover-export`
**Created**: 2026-03-14
**Status**: Draft
**Input**: User description: "Create a Home Assistant integration
that takes data from the Rental Control integration to create an
exported iCal for cleaning staff to know the time they have
between guests to turn over the property."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Basic Turnover Calendar (Priority: P1)

A property manager installs TurnoverCal, configures it to track
a Rental Control calendar, and receives a publicly accessible
iCal feed URL. Cleaning staff subscribe to this feed in their
preferred calendar app and see turnover windows — the gap between
one guest checking out and the next guest checking in — as
calendar events showing exactly when they need to clean.

**Why this priority**: This is the core value proposition.
Without turnover event generation and iCal export, no other
feature has meaning. It delivers immediate value to cleaning
staff the moment it is configured.

**Independent Test**: Can be fully tested by configuring a
Rental Control calendar with at least two consecutive guest
events, then subscribing to the generated iCal URL in any
standards-compliant calendar client and verifying the turnover
event appears between the two guest events.

**Acceptance Scenarios**:

1. **Given** a Rental Control calendar with Guest A checking out
   on March 10 at 11:00 and Guest B checking in on March 10 at
   15:00, **When** TurnoverCal processes these events, **Then**
   a turnover event is created from 11:00 to 15:00 on March 10.
2. **Given** a Rental Control calendar with Guest A checking out
   on March 10 at 11:00 and Guest B checking in on March 12 at
   15:00, **When** TurnoverCal processes these events, **Then**
   a turnover event is created spanning from March 10 at 11:00
   to March 12 at 15:00.
3. **Given** TurnoverCal is configured and running, **When** a
   calendar client requests the iCal feed URL, **Then** the
   response is a valid RFC 5545 iCalendar document containing
   all turnover events, served without requiring interactive
   authentication or authentication headers.
4. **Given** no upcoming guest events exist in Rental Control,
   **When** TurnoverCal processes the calendar, **Then** no
   turnover events are generated and the iCal feed returns a
   valid but empty calendar.

---

### User Story 2 - Historical Event Caching (Priority: P2)

A property manager needs to retain past turnover records even
after the STR platform removes old guest events. TurnoverCal
caches cleaning events for a configurable retention period
(defaulting to 6 weeks) so that cleaning staff and managers can
review past turnover history in their calendar app for scheduling
analysis and payment reconciliation.

**Why this priority**: STR platforms typically remove guest events
within a day of completion, causing Rental Control to lose
historical data. Without caching, past turnover events disappear
from the feed, eliminating accountability and audit capability.

**Independent Test**: Can be tested by creating guest events in
Rental Control, allowing TurnoverCal to generate turnover events,
then removing the source guest events from Rental Control and
verifying the turnover events persist in the iCal feed for the
configured retention period.

**Acceptance Scenarios**:

1. **Given** a turnover event was generated 3 weeks ago and the
   retention period is set to 6 weeks, **When** the source guest
   events are removed from Rental Control, **Then** the turnover
   event remains in the iCal feed.
2. **Given** a turnover event was generated 7 weeks ago and the
   retention period is set to 6 weeks, **When** the system
   performs its periodic cleanup, **Then** the turnover event is
   removed from the cache and no longer appears in the iCal feed.
3. **Given** the default configuration, **When** a user checks
   the retention setting, **Then** it is set to 6 weeks.
4. **Given** a user changes the retention period to 12 weeks,
   **When** turnover events older than 6 weeks but newer than 12
   weeks exist, **Then** those events remain in the iCal feed.

---

### User Story 3 - Keymaster Lock Early Completion (Priority: P3)

A property manager has a Keymaster-managed lock integrated with
Rental Control. When the cleaning staff unlocks the door using a
designated code during a multi-day turnover window, TurnoverCal
shortens the turnover event by moving DTEND to 00:00 the day
after the unlock, so the event extends through the end of the
unlock day rather than continuing to the original check-in date.
If the next guest check-in is on the same calendar day as the
unlock, no adjustment is made since the original end time
already reflects that day.

Additionally, when a Keymaster unlock occurs within a configurable
grace period before the scheduled checkout time (default 2 hours),
TurnoverCal moves the turnover event's DTSTART to the unlock time,
recognizing that the guest departed early and cleaning has begun.
This gives cleaning staff credit for the additional time. Unlocks
occurring earlier than the grace period before checkout are ignored
to avoid false positives from guests still occupying the property.

**Why this priority**: This is an enhancement that adds real-time
accuracy to turnover tracking. It depends on the core turnover
calendar (P1) and benefits from caching (P2) to retain the
adjusted events. Not all properties use Keymaster, so this is
optional functionality.

**Independent Test**: Can be tested by configuring a Rental
Control calendar with Keymaster lock management, creating a
multi-day turnover window, triggering the designated unlock
event, and verifying the turnover event end time is adjusted.

**Acceptance Scenarios**:

1. **Given** a turnover event spanning March 10 at 11:00 to
   March 12 at 15:00 with a Keymaster lock configured, **When**
   the cleaning staff unlock event occurs on March 10 at 14:30,
   **Then** DTEND is set to March 11 at 00:00, representing the
   turnover window extending through the end of March 10 (since the
   next guest check-in is on a different day).
2. **Given** a turnover event with a Keymaster lock configured,
   **When** no unlock event occurs during the turnover window,
   **Then** the turnover event retains its original end time
   (next guest check-in time).
3. **Given** the Rental Control integration is NOT configured
   with a Keymaster lock, **When** TurnoverCal processes events,
   **Then** all turnover events use the standard checkout-to-
   check-in calculation with no lock monitoring.
4. **Given** a turnover event spanning March 10 at 11:00 to
   March 10 at 15:00 with a Keymaster lock configured, **When**
   the cleaning staff unlock event occurs on March 10 at 12:00,
   **Then** the turnover event end time remains March 10 at
   15:00 (next guest check-in is on the same day as the unlock).
5. **Given** a guest checkout scheduled for March 10 at 11:00
   and a 2-hour early-unlock grace period, **When** the cleaning
   staff unlock event occurs on March 10 at 09:30, **Then**
   DTSTART is moved from 11:00 to 09:30, recognizing that
   cleaning began before the scheduled checkout.
6. **Given** a guest checkout scheduled for March 10 at 11:00
   and a 2-hour early-unlock grace period, **When** an unlock
   event occurs on March 10 at 07:00, **Then** the unlock is
   ignored because it falls outside the grace period (more than
   2 hours before checkout), and the turnover event is unchanged.

---

### User Story 4 - Manual Cleaning Signal (Priority: P3)

Property managers or cleaning staff need to signal that cleaning
has started when no Keymaster event fires — either because no
smart lock is installed, the door was left open by departing guests,
or the lock integration failed. TurnoverCal provides a Home
Assistant service call (`turnovercal.mark_cleaning_started`) that
has the same effect as a Keymaster unlock: it adjusts DTSTART if
called during the early-unlock grace period, or shortens DTEND if
called during an active turnover window. This service
can be triggered from HA automations, dashboard buttons, NFC tags,
or any other HA automation trigger.

**Why this priority**: Same phase as Keymaster support (P3) since
it shares the same turnover adjustment logic. Provides a critical
fallback for properties without smart locks and for edge cases
where lock events fail to fire.

**Independent Test**: Can be tested by creating a turnover window,
calling the service, and verifying the event times are adjusted
identically to a Keymaster unlock scenario.

**Acceptance Scenarios**:

1. **Given** an active turnover window from March 10 at 11:00 to
   March 12 at 15:00, **When** the
   `turnovercal.mark_cleaning_started` service is called on
   March 10 at 14:30, **Then**
   DTEND is adjusted identically to a Keymaster unlock (00:00 on
   March 11, since next check-in is on a different day).
2. **Given** a guest checkout scheduled for March 10 at 11:00 and
   a 2-hour early-unlock grace period, **When** the service is
   called on March 10 at 09:45, **Then** DTSTART is moved to
   09:45, recognizing early cleaning start.
3. **Given** no Keymaster lock is configured, **When** the service
   is called during a turnover window, **Then** the adjustment
   is applied without requiring any lock integration.
4. **Given** no active turnover window and no upcoming turnover
   within the grace period, **When** the service is called,
   **Then** the call is logged as a warning and no adjustment
   is made.

---

### Edge Cases

- What happens when two consecutive guest events have the same
  checkout and check-in time (back-to-back guests with no gap)?
  The turnover event MUST use a minimal duration (1 minute)
  rather than zero length to ensure visibility across all
  calendar clients, signaling that no meaningful cleaning gap
  exists.
- What happens when Rental Control is unavailable or returns
  errors? TurnoverCal MUST continue serving the cached iCal
  feed with the most recent known data and log the error.
- What happens when the next guest check-in time is before the
  current guest checkout time (booking overlap/error)?
  TurnoverCal MUST NOT generate a turnover event for negative
  time windows and MUST log a warning.
- What happens when TurnoverCal is first installed and no
  historical data exists? The feed MUST be valid but empty
  until guest events are processed.
- What happens when a Keymaster unlock event occurs outside
  of an active turnover window?
  - *Before the early-unlock grace period*: The unlock is
    ignored and no turnover adjustment is made (e.g., guest
    activity hours before checkout).
  - *Within the early-unlock grace period before checkout*
    (default 2 hours): The unlock is honored as an early
    departure — DTSTART moves to the unlock time (FR-017).
  - *After the next guest has checked in*: The unlock is
    ignored — the turnover window is already past.
- What happens when the Keymaster unlock event occurs at 23:58
  and the next guest check-in is at 00:15 the following day?
  "Same day" is determined by calendar date in local timezone,
  so these are different days. DTEND is set to 00:00 the
  following day, meaning the turnover window extends through the
  end of the unlock day. The 15-minute gap between the turnover
  end and guest check-in is expected — the turnover event tracks
  the cleaning completion date, not the full idle period.
- What happens when a guest event is modified in Rental Control
  (check-in/checkout time changes)? The corresponding turnover
  event MUST be recalculated to reflect the updated times.
- What happens after the last guest event in the calendar (no
  following guest)? TurnoverCal MUST generate a trailing
  turnover event starting at the last guest's checkout time with
  a duration equal to the configured trailing turnover duration
  (default 4 hours). This ensures cleaning staff are notified
  even when no subsequent booking exists. If a new guest event
  is later added after this checkout, the trailing event MUST be
  replaced by a standard turnover event spanning checkout to the
  new guest's check-in.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: TurnoverCal MUST integrate with the Rental Control
  Home Assistant integration to read guest event data (check-in
  and checkout times).
- **FR-002**: TurnoverCal MUST generate turnover events where
  the start time is the checkout time of the departing guest and
  the end time is the check-in time of the arriving guest.
  When no arriving guest follows a departure (the last event in
  the calendar), TurnoverCal MUST generate a trailing turnover
  event whose DTEND is DTSTART plus a configurable trailing
  turnover duration (default 4 hours). This trailing event MUST
  be replaced by a standard turnover event if a subsequent guest
  event is later added to the Rental Control calendar.
- **FR-003**: TurnoverCal MUST expose a publicly accessible iCal
  feed URL that does not require interactive authentication or
  authentication headers to access. Access is controlled by a
  secret URL token generated from a cryptographically secure
  random number generator. The token MUST NOT be derived from
  predictable values such as the instance identifier. The URL
  path MAY include a user-configurable prefix, but overrides
  MUST NOT remove or reduce the entropy of the token portion.
  The token MUST be revocable and regenerable through the
  integration options flow. The token MUST be treated as
  sensitive and redacted from logs, diagnostics, and error
  reports.
- **FR-004**: The iCal feed MUST conform to RFC 5545 and be
  consumable by any standards-compliant calendar client
  (Google Calendar, Apple Calendar, Outlook, etc.). Event
  times MUST be encoded using the local timezone configured
  in Home Assistant with a VTIMEZONE component included in
  the calendar to ensure correct interpretation across
  clients and time zones.
- **FR-005**: TurnoverCal MUST cache generated turnover events
  to retain them after the source guest events are removed from
  Rental Control by the STR platform.
- **FR-006**: The cache retention period MUST be configurable
  with a default value of 6 weeks.
- **FR-007**: Cached events that exceed the configured retention
  period MUST be automatically removed.
- **FR-008**: When the tracked Rental Control calendar is
  configured with a Keymaster lock, TurnoverCal MUST monitor
  the `keymaster_lock_state_changed` event for unlock actions
  matching a user-configured cleaning staff code slot number.
  The code slot number MUST be specified during setup and MUST
  be changeable via the options flow. Only unlock events whose
  `code_slot_num` matches the configured cleaning slot trigger
  turnover adjustments; all other unlock events (guest codes,
  manual unlocks, RF unlocks) MUST be ignored.
- **FR-009**: When a designated Keymaster unlock event occurs
  during a turnover window, TurnoverCal MUST recalculate the
  turnover event end time. "Same day" is determined by calendar
  date in the Home Assistant configured local timezone. If the
  next guest check-in falls on the same calendar day as the
  unlock event, the end time remains the original check-in time.
  Otherwise, DTEND is set to 00:00 on the day after the unlock,
  representing the turnover window extending through the end of
  the unlock day per RFC 5545 non-inclusive DTEND semantics.
- **FR-010**: TurnoverCal MUST update existing turnover events
  when the underlying guest events are modified in Rental
  Control (time changes, cancellations). Each turnover event
  MUST have a stable, deterministic UID preserved across
  recalculations and Keymaster adjustments, to prevent calendar
  clients from showing duplicates. The UID MUST be derived
  using a one-way transformation so that source guest event
  identifiers cannot be recovered from the UID value alone.
- **FR-011**: TurnoverCal MUST handle the case where no gap
  exists between guests (zero-duration turnover) by setting
  DTEND to DTSTART plus 1 minute, ensuring visibility across
  calendar clients.
- **FR-012**: TurnoverCal MUST NOT generate turnover events for
  negative time windows (overlapping bookings) and MUST log
  a warning when this condition is detected.
- **FR-013**: TurnoverCal MUST continue serving cached iCal data
  when Rental Control is temporarily unavailable.
- **FR-014**: Each turnover event in the iCal feed MUST include
  a meaningful summary identifying the property and turnover
  period. Summaries MUST NOT include sensitive guest information
  since the feed is publicly accessible.
- **FR-015**: TurnoverCal MUST be configurable through the
  standard Home Assistant integration setup flow.
- **FR-016**: The trailing turnover duration MUST be configurable
  with a default value of 4 hours (range: 1–24 hours). This
  duration is used for turnover events generated after the last
  guest checkout when no subsequent guest event exists.
- **FR-017**: When a Keymaster unlock event occurs within a
  configurable grace period before the scheduled checkout time
  (default 2 hours), TurnoverCal MUST move the turnover event's
  DTSTART to the unlock time, recognizing an early guest
  departure. Unlocks outside this grace period (earlier than the
  grace window before checkout) MUST be ignored.
- **FR-018**: The early-unlock grace period MUST be configurable
  with a default value of 2 hours (range: 0–12 hours). A value
  of 0 disables early-unlock detection entirely.
- **FR-019**: TurnoverCal MUST expose a Home Assistant service
  (`turnovercal.mark_cleaning_started`) that triggers the same
  turnover event adjustments as a Keymaster unlock event. The
  service MUST accept a `config_entry_id` parameter (or entity
  target) to identify which TurnoverCal instance to act on. The
  service MUST apply the same DTSTART grace-period logic (FR-017)
  and DTEND shortening logic (FR-009) as Keymaster events. This
  service provides a fallback for properties without Keymaster,
  for cases where lock events fail to fire, and for manual
  override scenarios.

### Key Entities

- **Turnover Event**: Represents the cleaning window between
  guests. Key attributes: start time (guest checkout), end time
  (next guest check-in or adjusted by lock event), property
  identifier, associated Rental Control calendar, status
  (scheduled, adjusted, completed), unique identifier.
- **Rental Control Calendar**: The source calendar from the
  Rental Control integration that provides guest event data.
  Attributes: calendar entity, optional Keymaster lock
  association.
- **Cached Event**: A persisted copy of a turnover event that
  survives removal of the source guest data. Attributes: all
  turnover event fields plus creation timestamp and expiration
  date based on retention policy.

## Assumptions

- Rental Control exposes guest event data (check-in/checkout
  times) through a Home Assistant calendar entity that
  TurnoverCal can read.
- Each Rental Control calendar tracks a single property;
  multiple properties require multiple TurnoverCal instances.
- The Keymaster unlock event is identifiable through the Home
  Assistant event system or entity state changes.
- The iCal feed URL is generated per TurnoverCal instance and
  remains stable across restarts.
- Home Assistant provides a mechanism for serving static HTTP
  endpoints (for the iCal feed).
- Cleaning staff have access to calendar applications that
  support iCal subscription feeds.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Cleaning staff can subscribe to the turnover feed
  and see accurate turnover windows within 5 minutes of
  TurnoverCal being configured.
- **SC-002**: Turnover events remain accessible in the feed for
  the full configured retention period (default 6 weeks) even
  after the STR platform removes the source data.
- **SC-003**: The iCal feed is consumable without modification
  by at least 3 major calendar clients (Google Calendar, Apple
  Calendar, Microsoft Outlook).
- **SC-004**: When a Keymaster unlock event occurs during a
  turnover window, the feed reflects the adjusted DTEND
  within 1 minute of the unlock event occurring. The adjusted
  DTEND represents the completion date (not the exact unlock
  time) per FR-009.
- **SC-005**: The iCal feed is accessible without interactive
  authentication from any network client that possesses the
  secret URL token and can reach the Home Assistant instance.
- **SC-006**: Property managers can configure TurnoverCal in
  under 3 minutes through the standard Home Assistant setup
  flow.
- **SC-007**: Zero-duration turnovers (back-to-back guests) are
  visible in the feed, alerting cleaning staff that no gap
  exists.
- **SC-008**: The iCal feed endpoint responds within 2 seconds
  under typical load (single property with up to 1 year of
  cached events).
