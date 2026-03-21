# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Data models for the TurnoverCal integration."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

_UID_PATTERN = re.compile(r"^[0-9a-f]{16}@turnovercal\.homeassistant$")


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
    created_from_midstay_cancellation: bool

    def __init__(  # noqa: PLR0913
        self,
        *,
        uid: str,
        summary: str,
        dtstart: datetime,
        dtend: datetime,
        timezone: str,
        source_checkout_id: str,
        source_checkin_id: str | None,
        created_at: datetime,
        status: str = "scheduled",
        is_trailing: bool = False,
        adjusted_by_lock: bool = False,
        lock_unlock_time: datetime | None = None,
        adjustment_source: str | None = None,
        original_dtend: datetime | None = None,
        original_dtstart: datetime | None = None,
        created_from_midstay_cancellation: bool = False,
    ) -> None:
        """Initialize a TurnoverEvent with validation.

        Raises ValueError if UID format is invalid or dtstart > dtend.
        Promotes dtend to dtstart + 1 minute when dtstart == dtend.
        """
        if not _UID_PATTERN.match(uid):
            msg = (
                "UID must match {hex16}@turnovercal.homeassistant "
                f"pattern, got '{uid}'"
            )
            raise ValueError(msg)

        if dtstart == dtend:
            dtend = dtstart + timedelta(minutes=1)

        if dtstart > dtend:
            msg = "dtstart must be before dtend"
            raise ValueError(msg)

        if is_trailing and source_checkin_id is not None:
            msg = "Trailing events must have source_checkin_id=None"
            raise ValueError(msg)

        if not is_trailing and source_checkin_id is None:
            msg = "Non-trailing events must have source_checkin_id"
            raise ValueError(msg)

        self.uid = uid
        self.summary = summary
        self.dtstart = dtstart
        self.dtend = dtend
        self.timezone = timezone
        self.source_checkout_id = source_checkout_id
        self.source_checkin_id = source_checkin_id
        self.created_at = created_at
        self.status = status
        self.is_trailing = is_trailing
        self.adjusted_by_lock = adjusted_by_lock
        self.lock_unlock_time = lock_unlock_time
        self.adjustment_source = adjustment_source
        self.original_dtend = original_dtend
        self.original_dtstart = original_dtstart
        self.created_from_midstay_cancellation = created_from_midstay_cancellation

    def to_dict(self) -> dict[str, Any]:
        """Serialize this event to a JSON-compatible dict.

        Local datetimes (dtstart, dtend, original_dtstart, original_dtend)
        are stored as naive ISO strings. UTC datetimes (created_at,
        lock_unlock_time) are stored with +00:00 offset.
        """
        _utc = ZoneInfo("UTC")
        return {
            "uid": self.uid,
            "summary": self.summary,
            "dtstart": self.dtstart.replace(tzinfo=None).isoformat(),
            "dtend": self.dtend.replace(tzinfo=None).isoformat(),
            "timezone": self.timezone,
            "source_checkout_id": self.source_checkout_id,
            "source_checkin_id": self.source_checkin_id,
            "created_at": self.created_at.astimezone(_utc).isoformat(),
            "status": self.status,
            "is_trailing": self.is_trailing,
            "adjusted_by_lock": self.adjusted_by_lock,
            "lock_unlock_time": (
                self.lock_unlock_time.astimezone(_utc).isoformat()
                if self.lock_unlock_time is not None
                else None
            ),
            "adjustment_source": self.adjustment_source,
            "original_dtend": (
                self.original_dtend.replace(tzinfo=None).isoformat()
                if self.original_dtend is not None
                else None
            ),
            "original_dtstart": (
                self.original_dtstart.replace(tzinfo=None).isoformat()
                if self.original_dtstart is not None
                else None
            ),
            "created_from_midstay_cancellation": (
                self.created_from_midstay_cancellation
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TurnoverEvent:
        """Deserialize a TurnoverEvent from a dict.

        Parses naive local ISO strings back into timezone-aware datetimes
        using the stored timezone field.
        """
        tz = ZoneInfo(data["timezone"])

        dtstart = datetime.fromisoformat(data["dtstart"]).replace(tzinfo=tz)
        dtend = datetime.fromisoformat(data["dtend"]).replace(tzinfo=tz)

        original_dtstart = None
        if data.get("original_dtstart") is not None:
            original_dtstart = datetime.fromisoformat(data["original_dtstart"]).replace(
                tzinfo=tz
            )

        original_dtend = None
        if data.get("original_dtend") is not None:
            original_dtend = datetime.fromisoformat(data["original_dtend"]).replace(
                tzinfo=tz
            )

        created_at = datetime.fromisoformat(data["created_at"])

        lock_unlock_time = None
        if data.get("lock_unlock_time") is not None:
            lock_unlock_time = datetime.fromisoformat(data["lock_unlock_time"])

        return cls(
            uid=data["uid"],
            summary=data["summary"],
            dtstart=dtstart,
            dtend=dtend,
            timezone=data["timezone"],
            source_checkout_id=data["source_checkout_id"],
            source_checkin_id=data.get("source_checkin_id"),
            created_at=created_at,
            status=data.get("status", "scheduled"),
            is_trailing=data.get("is_trailing", False),
            adjusted_by_lock=data.get("adjusted_by_lock", False),
            lock_unlock_time=lock_unlock_time,
            adjustment_source=data.get("adjustment_source"),
            original_dtend=original_dtend,
            original_dtstart=original_dtstart,
            created_from_midstay_cancellation=data.get(
                "created_from_midstay_cancellation",
                False,
            ),
        )


class CachedEventStore:
    """Persistent storage wrapper for turnover events."""

    version: int
    events: dict[str, TurnoverEvent]
    feed_token: str
    last_cleanup: datetime

    def __init__(
        self,
        *,
        version: int,
        events: dict[str, TurnoverEvent],
        feed_token: str,
        last_cleanup: datetime,
    ) -> None:
        """Initialize a CachedEventStore."""
        self.version = version
        self.events = events
        self.feed_token = feed_token
        self.last_cleanup = last_cleanup

    def to_dict(self) -> dict[str, Any]:
        """Serialize this store to a JSON-compatible dict."""
        return {
            "version": self.version,
            "events": {uid: evt.to_dict() for uid, evt in self.events.items()},
            "feed_token": self.feed_token,
            "last_cleanup": self.last_cleanup.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CachedEventStore:
        """Deserialize a CachedEventStore from a dict."""
        events = {
            uid: TurnoverEvent.from_dict(evt_data)
            for uid, evt_data in data.get("events", {}).items()
        }
        return cls(
            version=data["version"],
            events=events,
            feed_token=data["feed_token"],
            last_cleanup=datetime.fromisoformat(data["last_cleanup"]),
        )
