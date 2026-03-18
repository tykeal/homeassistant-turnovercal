# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Data models for the TurnoverCal integration.

Stub module: implementation pending (Phase 2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime


class TurnoverEvent:
    """A turnover cleaning window between consecutive guest stays."""

    uid: str
    summary: str
    dtstart: datetime
    dtend: datetime
    timezone: str
    source_checkout_id: str
    source_checkin_id: str | None
    created_at: datetime
    status: str
    is_trailing: bool
    adjusted_by_lock: bool
    lock_unlock_time: datetime | None
    adjustment_source: str | None
    original_dtend: datetime | None
    original_dtstart: datetime | None

    def __init__(self, **kwargs: Any) -> None:  # noqa: ANN401
        """Initialize a TurnoverEvent (stub: not yet implemented)."""
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:
        """Serialize this event to a JSON-compatible dict."""
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TurnoverEvent:
        """Deserialize a TurnoverEvent from a dict."""
        raise NotImplementedError


class CachedEventStore:
    """Persistent storage wrapper for turnover events."""

    version: int
    events: dict[str, TurnoverEvent]
    feed_token: str
    last_cleanup: datetime

    def __init__(self, **kwargs: Any) -> None:  # noqa: ANN401
        """Initialize a CachedEventStore (stub: not yet implemented)."""
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:
        """Serialize this store to a JSON-compatible dict."""
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CachedEventStore:
        """Deserialize a CachedEventStore from a dict."""
        raise NotImplementedError
