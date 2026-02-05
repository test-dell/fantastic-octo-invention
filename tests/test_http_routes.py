"""
Tests for HTTP routes.
"""

import pytest


class TestIndexRoute:
    """Tests for the index page."""

    def test_index_returns_200(self, client):
        """Index page should return 200."""
        response = client.get('/')
        assert response.status_code == 200

    def test_index_contains_expected_content(self, client):
        """Index page should contain game title or form."""
        response = client.get('/')
        assert b'<!DOCTYPE html>' in response.data or b'<html' in response.data


class TestRoomRoute:
    """Tests for the room page."""

    def test_room_returns_200(self, client):
        """Room page should return 200 for any room ID."""
        response = client.get('/room/ABC123')
        assert response.status_code == 200

    def test_room_with_lowercase_id(self, client):
        """Room page should work with lowercase ID."""
        response = client.get('/room/abc123')
        assert response.status_code == 200


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_returns_200(self, client):
        """Health endpoint should return 200 when healthy."""
        response = client.get('/health')
        assert response.status_code == 200

    def test_health_returns_json(self, client):
        """Health endpoint should return JSON."""
        response = client.get('/health')
        assert response.content_type == 'application/json'

    def test_health_contains_status(self, client):
        """Health response should contain status field."""
        response = client.get('/health')
        data = response.get_json()
        assert 'status' in data
        assert data['status'] == 'healthy'

    def test_health_contains_timestamp(self, client):
        """Health response should contain timestamp."""
        response = client.get('/health')
        data = response.get_json()
        assert 'timestamp' in data
