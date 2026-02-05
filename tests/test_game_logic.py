"""
Unit tests for game logic functions.
"""

import pytest
from app import (
    count_matches,
    validate_number,
    gen_room_code,
    gen_token,
    secrets_equal,
)
from config import DIGIT_COUNT, MIN_SECRET, MAX_SECRET, ROOM_ID_LENGTH, TOKEN_LENGTH


class TestCountMatches:
    """Tests for the count_matches function."""

    def test_all_match(self):
        """All digits match in same position."""
        assert count_matches("1234", "1234") == 4

    def test_no_match(self):
        """No digits match."""
        assert count_matches("1234", "5678") == 0

    def test_partial_match(self):
        """Some digits match in position."""
        assert count_matches("1234", "1243") == 2  # 1 and 2 match
        assert count_matches("1234", "1235") == 3  # 1, 2, 3 match

    def test_same_digits_wrong_position(self):
        """Same digits but wrong positions should not match."""
        assert count_matches("1234", "4321") == 0

    def test_one_match(self):
        """Only one digit matches."""
        assert count_matches("1234", "1567") == 1

    def test_boundary_values(self):
        """Test with boundary values."""
        assert count_matches("1000", "1000") == 4
        assert count_matches("9999", "9999") == 4
        assert count_matches("1000", "9999") == 0


class TestValidateNumber:
    """Tests for the validate_number function."""

    def test_valid_numbers(self):
        """Valid 4-digit numbers should pass."""
        assert validate_number("1000") is True
        assert validate_number("9999") is True
        assert validate_number("5432") is True
        assert validate_number("1234") is True

    def test_invalid_too_short(self):
        """Numbers with less than 4 digits should fail."""
        assert validate_number("123") is False
        assert validate_number("1") is False
        assert validate_number("") is False

    def test_invalid_too_long(self):
        """Numbers with more than 4 digits should fail."""
        assert validate_number("12345") is False
        assert validate_number("123456789") is False

    def test_invalid_below_min(self):
        """Numbers below MIN_SECRET should fail."""
        assert validate_number("0999") is False
        assert validate_number("0001") is False
        assert validate_number("0000") is False

    def test_invalid_non_numeric(self):
        """Non-numeric strings should fail."""
        assert validate_number("abcd") is False
        assert validate_number("12ab") is False
        assert validate_number("12.4") is False
        assert validate_number("-123") is False

    def test_invalid_none(self):
        """None should fail."""
        assert validate_number(None) is False

    def test_invalid_with_spaces(self):
        """Numbers with spaces should fail."""
        assert validate_number(" 1234") is False
        assert validate_number("1234 ") is False
        assert validate_number("12 34") is False


class TestGenRoomCode:
    """Tests for room code generation."""

    def test_default_length(self):
        """Generated code should have default length."""
        code = gen_room_code()
        assert len(code) == ROOM_ID_LENGTH

    def test_custom_length(self):
        """Generated code should respect custom length."""
        code = gen_room_code(length=10)
        assert len(code) == 10

    def test_uppercase_alphanumeric(self):
        """Generated code should be uppercase alphanumeric."""
        code = gen_room_code()
        assert code.isupper() or code.isdigit() or code.isalnum()
        assert code == code.upper()

    def test_uniqueness(self):
        """Generated codes should be unique (statistically)."""
        codes = [gen_room_code() for _ in range(100)]
        # With 6 chars from 36 symbols, collision in 100 is very unlikely
        assert len(set(codes)) >= 95


class TestGenToken:
    """Tests for token generation."""

    def test_default_length(self):
        """Generated token should have default length."""
        token = gen_token()
        assert len(token) == TOKEN_LENGTH

    def test_custom_length(self):
        """Generated token should respect custom length."""
        token = gen_token(length=64)
        assert len(token) == 64

    def test_alphanumeric(self):
        """Generated token should be alphanumeric."""
        token = gen_token()
        assert token.isalnum()

    def test_uniqueness(self):
        """Generated tokens should be unique."""
        tokens = [gen_token() for _ in range(100)]
        assert len(set(tokens)) == 100


class TestSecretsEqual:
    """Tests for constant-time string comparison."""

    def test_equal_strings(self):
        """Equal strings should return True."""
        assert secrets_equal("password", "password") is True
        assert secrets_equal("", "") is True
        assert secrets_equal("a", "a") is True

    def test_unequal_strings(self):
        """Unequal strings should return False."""
        assert secrets_equal("password", "passw0rd") is False
        assert secrets_equal("abc", "abd") is False
        assert secrets_equal("a", "b") is False

    def test_different_lengths(self):
        """Strings of different lengths should return False."""
        assert secrets_equal("short", "longer") is False
        assert secrets_equal("", "a") is False

    def test_case_sensitive(self):
        """Comparison should be case-sensitive."""
        assert secrets_equal("Password", "password") is False
        assert secrets_equal("ABC", "abc") is False
