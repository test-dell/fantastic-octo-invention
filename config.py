"""
Configuration settings for the Number Guessing Game.

This module centralizes all configuration constants and environment variables
to make the application easier to configure and maintain.
"""

import os
from typing import List

# =============================================================================
# Game Settings
# =============================================================================

DIGIT_COUNT: int = 4
"""Number of digits in the secret number."""

MIN_SECRET: int = 1000
"""Minimum valid secret number (inclusive)."""

MAX_SECRET: int = 9999
"""Maximum valid secret number (inclusive)."""

ROOM_ID_LENGTH: int = 6
"""Length of generated room codes."""

TOKEN_LENGTH: int = 32
"""Length of player authentication tokens."""

TURN_TIMEOUT_SECONDS: int = 60
"""Time limit for each turn in seconds (0 = disabled)."""

# =============================================================================
# Server Settings
# =============================================================================

DEBUG: bool = os.environ.get('DEBUG', 'false').lower() == 'true'
"""Enable debug mode. Set DEBUG=true in environment for development."""

HOST: str = os.environ.get('HOST', '0.0.0.0')
"""Host address to bind the server."""

PORT: int = int(os.environ.get('PORT', '5000'))
"""Port number for the server."""

SECRET_KEY: str = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
"""Flask secret key for session management."""

# =============================================================================
# Database Settings
# =============================================================================

DATABASE_PATH: str = os.environ.get('DB_PATH', 'game.db')
"""Path to the SQLite database file."""

# =============================================================================
# Admin Settings
# =============================================================================

ADMIN_KEY: str = os.environ.get('ADMIN_KEY', 'changeme')
"""Admin panel access key. Change this in production!"""

ADMIN_RATE_LIMIT: int = int(os.environ.get('ADMIN_RATE_LIMIT', '5'))
"""Maximum admin login attempts per minute."""

# =============================================================================
# CORS Settings
# =============================================================================

def get_cors_origins() -> List[str]:
    """
    Get allowed CORS origins from environment.

    Returns:
        List of allowed origin URLs, or ['*'] if not configured.
    """
    origins = os.environ.get('CORS_ORIGINS', '')
    if not origins:
        # Default to restrictive in production, permissive in debug
        if DEBUG:
            return ['*']
        return ['http://localhost:5000', 'http://127.0.0.1:5000']
    return [o.strip() for o in origins.split(',') if o.strip()]

CORS_ORIGINS: List[str] = get_cors_origins()
"""List of allowed CORS origins for Socket.IO connections."""

# =============================================================================
# Logging Settings
# =============================================================================

LOG_LEVEL: str = os.environ.get('LOG_LEVEL', 'DEBUG' if DEBUG else 'INFO')
"""Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)."""

LOG_FORMAT: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
"""Format string for log messages."""
