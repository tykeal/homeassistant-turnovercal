<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Requirements Checklist: TurnoverCal iCal Export

**Purpose**: Validate specification completeness and quality
before proceeding to planning
**Created**: 2026-03-14
**Feature**: [spec.md](../spec.md)

## Completeness

- [x] All user stories have acceptance scenarios with
      Given/When/Then format
- [x] Edge cases are identified and documented
- [x] Functional requirements cover all described behaviors
- [x] Key entities are defined with attributes
- [x] Success criteria are measurable

## Traceability

- [x] FR-001 through FR-002 map to User Story 1 (P1: Basic
      Turnover Calendar)
- [x] FR-003 through FR-004 map to User Story 1 (P1: iCal
      feed exposure)
- [x] FR-005 through FR-007 map to User Story 2 (P2:
      Historical Event Caching)
- [x] FR-008 through FR-009 map to User Story 3 (P3:
      Keymaster Lock Early Completion)
- [x] FR-010 through FR-012 map to Edge Cases (event
      modifications, zero-duration, overlaps)
- [x] FR-013 maps to Edge Case (Rental Control unavailability)
- [x] FR-014 through FR-015 map to general usability

## Consistency

- [x] RFC 5545 compliance referenced in FR-004 aligns with
      Constitution section III "User Experience Consistency"
      (see ../../.specify/memory/constitution.md)
- [x] Configurable retention period (FR-006) has a specified
      default (6 weeks)
- [x] Lock monitoring (FR-008/FR-009) is conditional on
      Keymaster configuration — does not break P1/P2
- [x] All "MUST" requirements use RFC 2119 language
      consistently

## Feasibility

- [x] Rental Control integration exists and exposes calendar
      entities in Home Assistant
- [x] Home Assistant supports custom HTTP endpoints for iCal
      serving (via aiohttp views)
- [x] Keymaster lock events are observable through HA event
      bus or entity state changes
- [x] Local file or database caching is feasible for event
      persistence

## Risks and Open Questions

- [x] Keymaster unlock event type is configurable during
      setup (user-selected event type). Specific configuration
      UI and available options are implementation details to be
      resolved during planning phase.
- [x] iCal URL path is auto-generated with optional
      user-configurable override
- [x] FR-009 end-time adjustment: uses next-guest check-in
      time if check-in is same calendar day (local timezone) as
      unlock; otherwise DTEND is 00:00 on the day after
      unlock, extending the window through the end of unlock
      day per RFC 5545 non-inclusive DTEND semantics
