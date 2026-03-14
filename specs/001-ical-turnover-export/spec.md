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
- What happens when the Keymaster unlock event occurs outside
  of an active turnover window (including before the checkout
  time while the departing guest is still present, or after the
  next guest has checked in)? The event MUST be ignored and no
  turnover adjustment made.
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

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: TurnoverCal MUST integrate with the Rental Control
  Home Assistant integration to read guest event data (check-in
  and checkout times).
- **FR-002**: TurnoverCal MUST generate turnover events where
  the start time is the checkout time of the departing guest and
  the end time is the check-in time of the arriving guest.
- **FR-003**: TurnoverCal MUST expose a publicly accessible iCal
  feed URL that does not require interactive authentication or
  authentication headers to access. Access is controlled by a
  secret URL token generated from a cryptographically secure
  random number generator. The token MUST NOT be derived from
  predictable values such as the instance identifier. The URL
  path MAY include a user-configurable prefix, but overrides
  MUST NOT remove or reduce the entropy of the token portion.
  The token MUST be revocable and regenerable through the
  integration options flow.
- **FR-004**: The iCal feed MUST conform to RFC 5545 and be
  consumable by any standards-compliant calendar client
  (Google Calendar, Apple Calendar, Outlook, etc.).
- **FR-005**: TurnoverCal MUST cache generated turnover events
  to retain them after the source guest events are removed from
  Rental Control by the STR platform.
- **FR-006**: The cache retention period MUST be configurable
  with a default value of 6 weeks.
- **FR-007**: Cached events that exceed the configured retention
  period MUST be automatically removed.
- **FR-008**: When the tracked Rental Control calendar is
  configured with a Keymaster lock, TurnoverCal MUST monitor
  for a configurable unlock event type (selected during setup)
  during active turnover windows.
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
  clients from showing duplicates. The UID derivation MUST NOT
  expose sensitive or correlatable source identifiers from guest
  events.
- **FR-011**: TurnoverCal MUST handle the case where no gap
  exists between guests (zero-duration turnover) by creating
  an event with a minimal duration (1 minute) to ensure
  visibility across calendar clients.
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
  turnover window, the feed reflects the adjusted end time
  within 1 minute of the event.
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
