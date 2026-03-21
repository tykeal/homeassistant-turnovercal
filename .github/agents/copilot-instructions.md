---
description: Development guidelines and conventions for the TurnoverCal Home Assistant integration.
applyTo: '**'
---

<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: MIT
-->

# TurnoverCal Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-03-20

## Active Technologies
- Python ≥3.13.2 (per pyproject.toml `requires-python`) + homeassistant ≥2026.2.0, icalendar ≥6.1.0, (002-cleanliness-state-tracking)
- HA Store (local JSON) — existing EventCache + new CleanlinessStateStore (002-cleanliness-state-tracking)

- Python 3.13 (Home Assistant 2026.2+ target) + `icalendar` ≥6.1.0 (RFC 5545 generation) (001-ical-turnover-export)

## Project Structure

```text
custom_components/turnovercal/
tests/
```

## Commands

uv run pytest tests/ && uv run ruff check custom_components/ tests/

## Code Style

Python 3.13 (Home Assistant 2026.2+ target): Follow standard conventions

## Recent Changes
- 002-cleanliness-state-tracking: Added Python ≥3.13.2 (per pyproject.toml `requires-python`) + homeassistant ≥2026.2.0, icalendar ≥6.1.0,

- 001-ical-turnover-export: Added Python 3.13 (Home Assistant 2026.2+ target) + `icalendar` ≥6.1.0 (RFC 5545 generation)

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
