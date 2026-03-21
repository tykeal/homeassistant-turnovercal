<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Feature Specification: Property Cleanliness State Tracking

**Feature Branch**: `002-cleanliness-state-tracking`
**Created**: 2025-07-18
**Status**: Draft
**Input**: User description: "Property Cleanliness State Tracking: Track a
per-property dirty or clean state that governs whether a turnover cleaning event
should be scheduled. The state is persisted so it survives restarts."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automatic Dirty Detection on Guest Check-In (Priority: P1)

As a property manager, I want the system to automatically recognize that my
property will need cleaning as soon as a guest arrives, so that the system
validates that a cleaning event exists (or creates a fallback) on the turnover
calendar without any manual intervention.

When a guest checks in (RC — the Rental Control
reservation calendar system — signals a check-in
event), the property transitions
to "dirty." The system validates that a turnover cleaning event already exists
for the corresponding check-out period. If no such event exists (safety-net
case), the system generates a fallback cleaning event starting at the scheduled
check-out time so the cleaning team knows the property needs attention.

**Why this priority**: This is the foundational behavior — the entire feature
depends on the system knowing when a property becomes dirty. Without automatic
dirty detection, no downstream cleaning logic can function.

**Independent Test**: Can be fully tested by configuring a property with a
single reservation that ends, then verifying the binary sensor shows "on"
(dirty) and
a cleaning event appears on the calendar.

**Acceptance Scenarios**:

1. **Given** a property with an incoming guest reservation, **When** the guest
   checks in (RC check-in event detected), **Then** the property's cleanliness
   state transitions to "dirty," the binary sensor reads "on," and the `phase`
   attribute reports `occupied`.
2. **Given** a property that just became dirty via check-in and no existing
   turnover event covers the corresponding check-out, **When** the system
   validates cleaning coverage, **Then** a fallback cleaning event is created
   starting at the scheduled check-out time with a duration equal to the
   configured `trailing_duration_hours`.
3. **Given** a property that just became dirty via check-in and an existing
   turnover event already covers the corresponding
   check-out, **When** the system
   validates cleaning coverage, **Then** no additional cleaning event is created
   (the existing turnover event suffices).
4. **Given** a property in the "dirty" state with `phase` = `occupied`, **When**
   the guest checks out (RC check-out event detected), **Then** the `phase`
   attribute transitions to `awaiting_cleaning` while the property remains
   dirty.

---

### User Story 2 - Clean Confirmation via Lock Code or Service (Priority: P1)

As a property manager, I want the property to begin the cleaning lifecycle when
my cleaner uses their designated lock code (transitioning to `being_cleaned`)
and to be confirmed clean either automatically after a configurable delay or
immediately when I manually confirm cleaning is complete, so that the system
accurately tracks cleaning progress and I can see at a glance which properties
are ready for the next guest.

**Why this priority**: Without a way to transition back to "clean," the dirty
state has no resolution. This completes the core dirty→clean lifecycle and makes
the binary sensor useful for dashboards and automations.

**Independent Test**: Can be fully tested by marking a property dirty, then
using either a lock code entry (verifying the `being_cleaned` phase and eventual
auto-transition to clean after delay) or the `mark_clean` service action
(verifying immediate clean), and confirming the binary sensor updates
accordingly.

**Acceptance Scenarios**:

1. **Given** a property in the "dirty" state with `phase` = `awaiting_cleaning`,
   **When** a cleaner unlocks the property using the designated cleaning lock
   code (adjusted_by_lock signal), **Then** the property remains in the "dirty"
   state, the `phase` attribute transitions to `being_cleaned`, and a delayed
   timer begins (default 3 hours, configurable via `cleaning_duration_hours`).
2. **Given** a property in the "dirty" state with `phase` = `being_cleaned` and
   the configured cleaning duration has elapsed, **When** the delay timer fires,
   **Then** the property transitions to "clean," the binary sensor reads "off,"
   and the `phase` attribute reports `clean`.
3. **Given** a property in the "dirty" state (any phase), **When** the property
   manager calls the `mark_clean` service action, **Then** the property
   transitions to "clean" immediately (no delay), the binary sensor reads "off,"
   and any active cleaning duration timer is cancelled.
4. **Given** a property that transitions to "clean," **When** the system
   evaluates cleaning events, **Then** no new automatic cleaning events are
   generated, but any existing lock-adjusted events remain on the calendar.

---

### User Story 3 - Binary Sensor Visibility on Dashboard (Priority: P1)

As a property manager with multiple vacation rentals, I want each property to
have a binary sensor showing dirty or clean status, so that I can build a
dashboard overview of all my properties and create automations based on
cleanliness state.

**Why this priority**: The binary sensor is the primary user-facing output of
the feature. It makes the dirty/clean state visible, actionable, and automatable
within Home Assistant.

**Independent Test**: Can be fully tested by loading the integration and
verifying the binary sensor entity appears under the existing device with
correct on/off states matching the property's cleanliness.

**Acceptance Scenarios**:

1. **Given** a property with the TurnoverCal integration configured, **When**
   the integration loads, **Then** a binary sensor entity appears under the
   property's existing device with an entity ID consistent
   with other TurnoverCal entities (for example,
   `binary_sensor.<property>_cleanliness`, derived from
   the config entry title and a `cleanliness` translation
   key).
2. **Given** a property in the "dirty" state, **When** viewing the binary
   sensor, **Then** the state reads "on" and additional context attributes
   include when the state last changed, the reason for the transition, and the
   current `phase` (`occupied`, `awaiting_cleaning`, or `being_cleaned`).
3. **Given** a property in the "clean" state, **When** viewing the binary
   sensor, **Then** the state reads "off" and the `phase` attribute reports
   `clean`.

---

### User Story 4 - Mid-Stay Cancellation Triggers Dirty State (Priority: P2)

As a property manager, I want the system to recognize that a property needs
cleaning when a booking is cancelled while the guest is mid-stay, so that even
though the booking disappears from the reservation calendar, a cleaning event is
still generated.

**Why this priority**: This covers an important but less common scenario — a
guest leaving early due to cancellation. It prevents the "orphaned dirty
property" problem where a booking vanishes and no one remembers to clean.

**Independent Test**: Can be fully tested by simulating a booking removal while
the guest's stay is active, then verifying the dirty state and cleaning event
persist even after the source booking is gone.

**Acceptance Scenarios**:

1. **Given** a property with an active guest stay
   (check-in has passed, check-out has not), **When**
   the booking is removed from the reservation calendar,
   **Then** the property transitions to "dirty" with `phase` =
   `awaiting_cleaning` (the guest's stay is terminated).
2. **Given** a cleaning event was created due to a mid-stay cancellation,
   **When** the source booking disappears from the reservation calendar
   entirely, **Then** the cleaning event remains on the turnover calendar (it is
   not removed).
3. **Given** a property made dirty by a mid-stay cancellation, **When** no one
   marks the property clean, **Then** the dirty state and cleaning event persist
   indefinitely (until explicitly resolved).

---

### User Story 5 - Force Dirty via Service Action (Priority: P2)

As a property manager, I want to force a property into the "dirty" state at any
time via a service action, so that I can trigger a cleaning event when I
discover the property needs re-cleaning (for example, after an inspection
reveals issues).

**Why this priority**: Provides manual override capability for real-world
situations that automated detection cannot cover (pest discovery, maintenance
mess, quality inspection failure).

**Independent Test**: Can be fully tested by calling the `mark_dirty` service
action on a clean property and verifying the binary sensor changes and a
cleaning event appears.

**Acceptance Scenarios**:

1. **Given** a property in the "clean" state with no upcoming cleaning events,
   **When** the property manager calls the `mark_dirty` service action, **Then**
   the property transitions to "dirty" with `phase` = `awaiting_cleaning`, and
   an immediate cleaning event is created with duration equal to trailing
   duration hours.
2. **Given** a property already in the "dirty" state, **When** the property
   manager calls the `mark_dirty` service action, **Then** the state remains
   "dirty" and no duplicate cleaning event is created if one already exists.

---

### User Story 6 - State Persistence Across Restarts (Priority: P2)

As a property manager, I want the dirty/clean state to survive Home Assistant
restarts and integration reloads, so that I never lose track of which properties
need cleaning due to a system reboot.

**Why this priority**: Without persistence, a restart could silently reset a
dirty property to an unknown state, causing missed cleanings.

**Independent Test**: Can be fully tested by setting a property to dirty,
restarting the integration, and verifying the binary sensor still reads "on"
(dirty) after restart.

**Acceptance Scenarios**:

1. **Given** a property in the "dirty" state, **When** Home Assistant restarts,
   **Then** the property remains in the "dirty" state and the binary sensor
   reads "on" immediately after startup.
2. **Given** a property in the "clean" state, **When** the integration is
   reloaded, **Then** the property remains in the "clean" state.
3. **Given** a cleaning event created from a mid-stay cancellation, **When**
   Home Assistant restarts, **Then** the cleaning event is still present on the
   turnover calendar.
4. **Given** a property in the "clean" state and a guest check-in occurred while
   Home Assistant was down, **When** Home Assistant restarts and performs entity
   state reconciliation, **Then** the property transitions to "dirty" with
   `phase` = `occupied` and the system validates cleaning event coverage for the
   corresponding check-out.

---

### Edge Cases

- What happens when a property has back-to-back reservations with no gap? When
  the first guest checks in, the property becomes dirty. The existing turnover
  event from normal computation covers the cleaning between the first check-out
  and next check-in — the check-in validation confirms this and no fallback
  event is generated.
- What happens when a property is marked clean while a cleaning event is
  actively in progress (the cleaner is still on-site)? The state transitions to
  clean; the existing lock-adjusted event is preserved. No new events are
  generated.
- What happens when two dirty triggers fire in rapid succession (e.g., a
  check-out followed immediately by a cancellation of the next booking)? The
  property remains dirty from the first trigger. The second trigger does not
  create a duplicate cleaning event if one already exists.
- What happens when the reservation calendar is temporarily unavailable? The
  dirty/clean state is not affected by polling failures — the last known state
  is preserved. Cleaning events already generated remain intact.
- What happens if Home Assistant was down during a guest's check-in? On startup,
  entity state reconciliation detects the guest is currently staying via RC
  entity state. The system triggers the check-in dirty transition (property
  becomes dirty, `phase` = `occupied`, cleaning event coverage validated). No
  check-in events are lost due to downtime.
- What happens when a property is first configured with no prior history? The
  initial state is "clean" (no cleaning needed until the first guest checks in).
- What happens when a booking is removed but the guest has not yet checked in
  (cancellation before stay begins)? No dirty transition occurs — the property
  was never occupied, so no cleaning is needed.
- What happens when the `mark_clean` service is called on a property that is
  already clean? The call succeeds silently with no state change and no side
  effects.
- What happens when `mark_dirty` is called during a guest's active stay (guest
  is still in the property)? The property is likely already dirty from the
  check-in trigger. If already dirty, the state remains dirty with `phase` =
  `occupied` and no duplicate cleaning event is created. If somehow clean (e.g.,
  false clean trigger), the state transitions to dirty with `phase` = `occupied`
  (guest is present) and an immediate cleaning event is created starting at the
  current time if none exists.
- What happens when a cleaner uses their lock code but the cleaning duration
  timer has not yet elapsed? The property remains dirty with `phase` =
  `being_cleaned`. The binary sensor still reads "on" until the timer fires or
  `mark_clean` is called.
- What happens when `mark_clean` is called while the property is in
  `being_cleaned` phase? The `mark_clean` service action immediately transitions
  to "clean," cancels the active cleaning duration timer, and the binary sensor
  reads "off."
- What happens when `mark_dirty` is called while the property is in
  `being_cleaned` phase? The `mark_dirty` service resets the property to "dirty"
  with `phase` = `awaiting_cleaning`, cancels the active cleaning duration
  timer, and validates cleaning event coverage. The cleaner's work is discarded.
- What happens when a guest checks in while the property is in `being_cleaned`
  phase? The guest check-in takes priority: the cleaning duration timer is
  cancelled, the property remains dirty, `phase` transitions to `occupied`, and
  cleaning event coverage is validated for the new guest's check-out.
- What happens if Home Assistant restarts while a property is in `being_cleaned`
  phase with an active cleaning duration timer? The persisted state includes the
  `being_cleaned` phase and the timer's target completion time. On restart, the
  system reconstitutes the timer from the persisted target time. If the target
  time has already passed during downtime, the property transitions to "clean"
  immediately on startup.

## Requirements *(mandatory)*

### Functional Requirements

#### State Management

- **FR-001**: System MUST maintain a per-property cleanliness state with exactly
  two values: "dirty" and "clean."
- **FR-002**: System MUST persist the cleanliness state so it survives Home
  Assistant restarts and integration reloads.
- **FR-003**: System MUST initialize new properties with the "clean" state when
  first configured.
- **FR-004**: System MUST record the timestamp and reason for each state
  transition.

#### Dirty Triggers

- **FR-005**: System MUST transition a property to "dirty" when a guest check-in
  event is detected (RC signals guest arrival at the property).
- **FR-005a**: On check-in dirty trigger, the system MUST first validate that a
  turnover cleaning event already exists for the corresponding check-out period.
  Only if no such event exists MUST the system create a fallback cleaning event
  starting at the scheduled check-out time with a duration equal to
  `trailing_duration_hours`.
- **FR-005b**: System MUST consume RC-provided check-in and check-out events or
  state changes via real-time HA event listeners to detect guest arrivals and
  departures during normal operation.
- **FR-005c**: On startup or integration reload, the system MUST perform entity
  state reconciliation — checking the current state of RC-provided entities to
  detect any guest check-ins or check-outs that occurred during downtime — and
  triggering the appropriate dirty/phase state transitions for any missed
  events.
- **FR-006**: System MUST transition a property to "dirty" when a booking is
  removed from the reservation calendar while the guest is mid-stay (check-in
  time has passed but check-out time has not).
- **FR-007**: System MUST detect mid-stay cancellations by comparing the current
  set of active reservations against the previously known set during each
  polling cycle.
- **FR-008**: System MUST NOT transition to "dirty" when a booking is cancelled
  before the guest's check-in time (pre-arrival cancellation).

#### Clean Triggers

- **FR-009**: When a cleaning lock code entry is detected (the same
  adjusted_by_lock signal used for existing cleaning confirmation) and the
  property is dirty with `phase` = `awaiting_cleaning`, the system MUST
  transition the `phase` to `being_cleaned` (the property remains in the "dirty"
  state) and start the cleaning duration timer. The property does NOT transition
  directly to "clean" on lock code entry. If the property's `phase` is not
  `awaiting_cleaning` (e.g., `occupied`), the lock code entry performs only its
  existing event-adjustment behavior without changing the phase.
- **FR-009a**: After transitioning to `being_cleaned`, the system MUST start a
  delayed timer equal to the configured `cleaning_duration_hours` (default: 3
  hours). When the timer fires, the system MUST automatically transition the
  property to "clean."
- **FR-009b**: System MUST provide a configurable `cleaning_duration_hours`
  option (per config entry) that controls the delay between cleaner lock code
  entry and automatic clean transition. Default value: 3 hours. Minimum value: 0
  (which means immediate transition, equivalent to legacy behavior). The value
  is specified as a decimal number of hours. This option MUST be exposed in the
  integration's config flow (options flow) so property managers can adjust it
  without YAML editing.
- **FR-009c**: If `mark_clean` is called while a cleaning duration timer is
  active, the timer MUST be cancelled and the property MUST transition to
  "clean" immediately.
- **FR-009d**: If `mark_dirty` is called while a cleaning duration timer is
  active, the timer MUST be cancelled and the property MUST transition to
  "dirty" with `phase` = `awaiting_cleaning`.
- **FR-009e**: If a guest check-in occurs while a cleaning duration timer is
  active, the timer MUST be cancelled, the property MUST remain dirty with
  `phase` = `occupied`, and cleaning event coverage MUST be validated for the
  new guest's check-out.
- **FR-009f**: The cleaning duration timer's target completion time MUST be
  persisted so it survives Home Assistant restarts. On restart, if the target
  time has passed, the system MUST transition to "clean" immediately; otherwise,
  the system MUST reconstitute the timer for the remaining duration.
- **FR-010**: System MUST transition a property to "clean" immediately (no
  delay) when the property manager calls the `mark_clean` service action,
  regardless of the current phase. Any active cleaning duration timer MUST be
  cancelled.

#### Manual Override

- **FR-011**: System MUST provide a `turnovercal.mark_dirty` service action that
  forces a property to the "dirty" state regardless of its current state.
- **FR-012**: System MUST provide a `turnovercal.mark_clean` service action that
  forces a property to the "clean" state regardless of its current state.
- **FR-013**: Both service actions MUST accept targeting by entity (binary
  sensor or calendar) or by config entry ID, consistent with the existing
  `mark_cleaning_started` service pattern.

#### Cleaning Event Generation

- **FR-014**: When a property transitions to "dirty" via check-in trigger, the
  system MUST validate that a turnover cleaning event exists for the
  corresponding check-out. If none exists, the system MUST generate a fallback
  cleaning event.
- **FR-015**: Fallback cleaning events from check-in validation MUST start at
  the scheduled check-out time and have a duration equal to the configured
  `trailing_duration_hours`. Immediate cleaning events from `mark_dirty` service
  actions MUST start at the current time.
- **FR-016**: System MUST NOT generate a new automatic cleaning event if one
  already exists for the current dirty period.
- **FR-017**: When a property transitions to "clean," the system MUST stop
  generating new automatic cleaning events.
- **FR-018**: Existing lock-adjusted events MUST be preserved when a property
  transitions to "clean" (they are not removed or modified).
- **FR-019**: Cleaning events created from mid-stay cancellations MUST be
  preserved even if the source booking disappears from the reservation calendar.

#### Binary Sensor

- **FR-020**: System MUST expose the cleanliness state as a `binary_sensor`
  entity under the property's existing device.
- **FR-021**: The binary sensor MUST report "on" when the property is dirty and
  "off" when the property is clean.
- **FR-022**: The binary sensor MUST include attributes for the last state
  change timestamp, the reason for the transition (e.g., "guest_checkin,"
  "mid_stay_cancellation," "lock_code_entry," "cleaning_duration_elapsed,"
  "service_call_mark_clean," "service_call_mark_dirty"), and a `phase` attribute
  indicating the property's lifecycle phase.
- **FR-022a**: The `phase` attribute MUST report one of exactly four values:
  `occupied` when a guest is actively staying (between check-in and check-out),
  `awaiting_cleaning` after the guest checks out while the property remains
  dirty and no cleaner has started, `being_cleaned` after a cleaning lock code
  entry while the cleaning duration timer is active, and `clean` when the
  property is in the clean state. The full phase
  lifecycle is a repeating cycle starting from `clean`:
  `clean` → `occupied` → `awaiting_cleaning` →
  `being_cleaned` → `clean`.
- **FR-022b**: On detection of a guest check-out event (while the property is
  dirty), the system MUST transition the `phase` attribute from `occupied` to
  `awaiting_cleaning`. On a mid-stay cancellation dirty trigger, the `phase`
  MUST be set to `awaiting_cleaning` (the guest's stay is terminated). On a
  `mark_dirty` service call when no guest is actively staying, the `phase` MUST
  be set to `awaiting_cleaning`. On detection of a cleaning lock code entry
  (while phase is `awaiting_cleaning`), the system MUST transition the `phase`
  to `being_cleaned`. On cleaning duration timer expiration, the system MUST
  transition the `phase` to `clean`. The `awaiting_cleaning` phase is the
  canonical value for all dirty-but-no-cleaner-started states; the
  `being_cleaned` phase indicates active cleaning in progress.
- **FR-023**: The binary sensor entity ID MUST be derived
  using this integration's standard naming convention
  (config entry title + translation key for the
  cleanliness binary sensor) rather than a hard-coded
  `turnovercal_<property_name>_dirty` pattern. The
  translation key for this sensor MUST be stable so that
  the resulting entity ID remains predictable for
  automations.

### Key Entities

- **Cleanliness State**: Represents whether a property is dirty or clean. Key
  attributes: current state (dirty/clean), current phase (`occupied`,
  `awaiting_cleaning`, `being_cleaned`, `clean`), last transition timestamp,
  transition reason, cleaning duration timer target time (when in
  `being_cleaned` phase), associated config entry. Persisted independently of
  calendar events. One per property.
- **Immediate Cleaning Event**: A turnover event generated on-demand when a
  property is dirty and no existing turnover covers the cleaning need.
  Distinguished from regular turnover events and trailing events. Linked to the
  dirty state rather than to a specific booking pair. Preserved across polling
  cycles until the property is cleaned or the event expires.
- **Binary Sensor Entity**: The user-facing representation of the cleanliness
  state. Belongs to the same device as the existing calendar and sensor
  entities. Exposes state attributes for dashboard display and automation
  triggers, including a `phase` attribute (`occupied`, `awaiting_cleaning`,
  `being_cleaned`, `clean`) to distinguish sub-states within the dirty/cleaning
  lifecycle. The full phase lifecycle is as defined
  in **FR-022b**, including the cyclic `clean` →
  `occupied` transition.

### Assumptions

- The existing `adjusted_by_lock` signal (from Keymaster lock code entry or
  `mark_cleaning_started` service) will serve triple duty: it continues to
  adjust turnover event timing as it does today, it transitions the property's
  `phase` to `being_cleaned`, and it starts the cleaning duration timer. The
  property transitions to "clean" only after the configured
  `cleaning_duration_hours` delay (default 3 hours) or when `mark_clean` is
  called. No separate "cleaning complete" signal is needed beyond the timer
  expiration.
- Mid-stay cancellation detection relies on comparing the set of active
  reservations between polling cycles. If a reservation disappears while its
  stay period overlaps "now," this constitutes a mid-stay cancellation.
- The `trailing_duration_hours` configuration option already exists and is
  reused for immediate cleaning event duration. A new `cleaning_duration_hours`
  configuration option is introduced to control the delay between cleaner lock
  code entry and automatic clean transition (default: 3 hours).
- On startup or integration reload, the system performs entity state
  reconciliation against RC-provided entities to detect guest arrivals or
  departures that occurred during downtime. This ensures no missed check-in
  events leave a property incorrectly clean. During normal operation, real-time
  event listeners handle detection immediately.
- RC (the reservation calendar system) is adding guest check-in/check-out
  tracking. These will be exposed as HA events or entity state changes that
  TurnoverCal can monitor. The check-in event triggers the dirty transition; the
  check-out event is used to anchor the fallback cleaning event start time.
- Service actions (`mark_dirty`, `mark_clean`) are integration-level services
  (prefixed with `turnovercal.`) consistent with the existing
  `mark_cleaning_started` pattern.
- The binary sensor uses the `problem` device class, which aligns with Home
  Assistant conventions for "something needs attention" indicators.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of guest check-ins result in the property's binary sensor
  transitioning to "on" (dirty) within one event processing cycle of the
  check-in detection.
- **SC-002**: 100% of mid-stay cancellations result in the property becoming
  dirty within one polling cycle of the booking's removal, and the resulting
  cleaning event persists even after the source booking is fully gone.
- **SC-003**: Lock code entry transitions the property to `being_cleaned` within
  5 seconds, with automatic transition to "clean" after the configured
  `cleaning_duration_hours` delay (default 3 hours). The `mark_clean` service
  action transitions the property to "clean" immediately within 5 seconds.
- **SC-004**: Property managers can force any property to dirty in a single
  action (service call), with an immediate cleaning event appearing on the
  calendar within 5 seconds.
- **SC-005**: The cleanliness state survives 100% of Home Assistant restarts and
  integration reloads — the binary sensor reports the correct pre-restart state
  immediately upon startup.
- **SC-006**: Zero orphaned dirty properties — every dirty transition has a
  visible cleaning event on the turnover calendar, either from the standard
  turnover computation or from the immediate cleaning event fallback.
- **SC-007**: Zero false dirty transitions — pre-arrival booking cancellations
  do not trigger the dirty state.

## Clarifications

### Session 2026-03-20

- Q: When the check-in dirty trigger fires and no turnover cleaning event
  exists, should the fallback cleaning event start immediately or be deferred to
  check-out time? → A: Deferred start at check-out
  time. This is a safety-net case
  — the turnover cleaning event should already exist from normal turnover
  computation. The check-in dirty trigger primarily validates that a cleaning
  event exists; it only creates a fallback if none exists.
- Q: Should the binary sensor expose sub-states to distinguish between "guest is
  currently staying" and "guest left, awaiting cleaning"? → A: Yes. Add a
  `phase` attribute on the binary sensor: `occupied` (guest actively staying) →
  `awaiting_cleaning` (post-check-out, property still dirty). When clean, phase
  reports `clean`.
- Q: How should TurnoverCal detect RC check-in/check-out signals — event
  listener, polling, or both? → A: Both. Real-time HA event listener for
  detection during normal operation, plus entity state reconciliation on
  startup/reload to catch any check-in or check-out events missed during
  downtime.
- Q: Should `mark_dirty` (manual) and mid-stay cancellation use the same
  `awaiting_cleaning` phase as post-check-out, or introduce a distinct phase? →
  A: Reuse `awaiting_cleaning` for all dirty-but-no-guest cases (manual
  `mark_dirty`, mid-stay cancellation, post-check-out). No new phase values
  needed for those cases; the new `being_cleaned` phase is exclusively for
  post-lock-code-entry cleaning in progress.
- Q: What phase should the property enter when a cleaner uses their lock code? →
  A: New `being_cleaned` phase. The dirty-phase
  sub-lifecycle is: `occupied` →
  `awaiting_cleaning` → `being_cleaned` → `clean`. Lock code entry transitions
  to `being_cleaned`, not directly to `clean`.
- Q: Should the property be marked clean immediately when the cleaner code is
  used? → A: No. The property transitions to `clean` after a configurable delay
  (`cleaning_duration_hours`, default 3 hours) to allow cleaners time to finish.
- Q: Should `mark_clean` service action also use the delayed transition? → A:
  No. `mark_clean` transitions to `clean` immediately (no delay). This is the
  property manager override path. Any active cleaning duration timer is
  cancelled.
- Q: What are the complete set of phase attribute values? → A: Four values:
  `clean` (ready), `occupied` (guest checked in), `awaiting_cleaning`
  (post-check-out/manual dirty, waiting for cleaners), `being_cleaned` (cleaner
  code used, auto-transitions to `clean` after configurable delay).
