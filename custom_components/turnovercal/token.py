# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Feed token generation and validation."""

from __future__ import annotations

import hmac
import secrets


def generate_token() -> str:
    """Generate a cryptographically secure URL-safe feed token."""
    return secrets.token_urlsafe(32)


def validate_token(stored_token: str, provided_token: str) -> bool:
    """Validate a provided token against the stored token.

    Uses constant-time comparison to prevent timing attacks.
    Returns False if either token is empty.
    """
    if not stored_token or not provided_token:
        return False
    return hmac.compare_digest(stored_token, provided_token)
