"""
Pytest configuration and fixtures for the Number Guessing Game tests.
"""

import os
import pytest
import tempfile

# Set test environment before importing app
os.environ['DEBUG'] = 'false'

from app import app, socketio, init_db, rooms_runtime, rooms_lock


@pytest.fixture(scope='function')
def test_app():
    """Create a test Flask application with a temporary database."""
    # Create temporary database
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.environ['DB_PATH'] = db_path

    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'

    # Reinitialize database
    init_db()

    yield app

    # Cleanup
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture(scope='function')
def client(test_app):
    """Create a test client for HTTP requests."""
    return test_app.test_client()


@pytest.fixture(scope='function')
def socketio_client(test_app):
    """Create a Socket.IO test client."""
    return socketio.test_client(test_app)


@pytest.fixture(scope='function')
def clean_runtime():
    """Ensure rooms_runtime is clean before each test."""
    with rooms_lock:
        rooms_runtime.clear()
    yield
    with rooms_lock:
        rooms_runtime.clear()
