# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

"""Tests for feed token generation and validation."""

from __future__ import annotations

import hmac
from unittest.mock import patch

from custom_components.turnovercal.token import generate_token, validate_token

# ---------------------------------------------------------------------------
# generate_token
# ---------------------------------------------------------------------------


class TestGenerateToken:
    """Tests for generate_token() function."""

    def test_returns_string(self) -> None:
        """generate_token() returns a string."""
        token = generate_token()
        assert isinstance(token, str)

    def test_returns_43_character_url_safe_base64(self) -> None:
        """generate_token() returns a 43-character URL-safe base64 string."""
        token = generate_token()
        assert len(token) == 43
        # URL-safe base64 uses only these characters (no padding)
        allowed = set(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        )
        assert all(c in allowed for c in token)

    def test_returns_different_values_each_call(self) -> None:
        """generate_token() returns different values on each call."""
        tokens = {generate_token() for _ in range(10)}
        assert len(tokens) == 10


# ---------------------------------------------------------------------------
# validate_token
# ---------------------------------------------------------------------------


class TestValidateToken:
    """Tests for validate_token() function."""

    def test_matching_tokens_return_true(self) -> None:
        """validate_token returns True for matching tokens."""
        token = generate_token()
        assert validate_token(token, token) is True

    def test_non_matching_tokens_return_false(self) -> None:
        """validate_token returns False for non-matching tokens."""
        token1 = generate_token()
        token2 = generate_token()
        assert validate_token(token1, token2) is False

    def test_rejects_empty_string(self) -> None:
        """validate_token rejects empty string as provided token."""
        stored = generate_token()
        assert validate_token(stored, "") is False

    def test_rejects_empty_stored_token(self) -> None:
        """validate_token rejects empty string as stored token."""
        provided = generate_token()
        assert validate_token("", provided) is False

    def test_rejects_both_empty(self) -> None:
        """validate_token rejects both tokens being empty."""
        assert validate_token("", "") is False

    def test_uses_constant_time_comparison(self) -> None:
        """validate_token uses hmac.compare_digest for timing safety."""
        with patch.object(
            hmac,
            "compare_digest",
            wraps=hmac.compare_digest,
        ) as mock_compare:
            token = generate_token()
            validate_token(token, token)
            mock_compare.assert_called_once()

    def test_partial_match_returns_false(self) -> None:
        """validate_token returns False when tokens partially match."""
        token = generate_token()
        # Corrupt last character
        corrupted = token[:-1] + ("a" if token[-1] != "a" else "b")
        assert validate_token(token, corrupted) is False
