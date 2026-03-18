# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Feed token generation and validation.

Stub module: implementation pending (Phase 2).
"""

from __future__ import annotations


def generate_token() -> str:
    """Generate a cryptographically secure URL-safe feed token."""
    raise NotImplementedError


def validate_token(stored_token: str, provided_token: str) -> bool:
    """Validate a provided token against the stored token."""
    raise NotImplementedError
