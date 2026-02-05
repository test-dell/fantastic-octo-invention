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


class TestAdminRoutes:
    """Tests for admin panel routes."""

    def test_admin_without_key_returns_401(self, client):
        """Admin without key should return 401."""
        response = client.get('/admin')
        assert response.status_code == 401

    def test_admin_with_wrong_key_returns_403(self, client):
        """Admin with wrong key should return 403."""
        response = client.get('/admin', headers={'X-Admin-Key': 'wrong-key'})
        assert response.status_code == 403

    def test_admin_with_correct_key_returns_200(self, client, admin_headers):
        """Admin with correct key should return 200."""
        response = client.get('/admin', headers=admin_headers)
        assert response.status_code == 200

    def test_admin_with_key_in_query(self, client):
        """Admin with key in query string should work."""
        response = client.get('/admin?key=test-admin-key')
        assert response.status_code == 200

    def test_admin_kill_nonexistent_room(self, client, admin_headers):
        """Killing a non-existent room should redirect to admin."""
        response = client.get('/admin/kill/NONEXISTENT', headers=admin_headers)
        # Should redirect back to admin
        assert response.status_code in (200, 302)

    def test_admin_reset_nonexistent_room(self, client, admin_headers):
        """Resetting a non-existent room should redirect to admin."""
        response = client.get('/admin/reset/NONEXISTENT', headers=admin_headers)
        # Should redirect back to admin
        assert response.status_code in (200, 302)


class TestAdminRateLimiting:
    """Tests for admin rate limiting."""

    def test_rate_limit_not_triggered_within_limit(self, client):
        """Should allow requests within rate limit."""
        for _ in range(5):
            response = client.get('/admin', headers={'X-Admin-Key': 'wrong-key'})
            # Should get 403 (forbidden) not 429 (rate limited)
            assert response.status_code == 403

    def test_rate_limit_triggered_after_limit(self, client):
        """Should return 429 after exceeding rate limit."""
        # Make 6 requests (limit is 5 per minute)
        for i in range(6):
            response = client.get('/admin', headers={'X-Admin-Key': 'wrong-key'})

        # The 6th request should be rate limited
        assert response.status_code == 429
