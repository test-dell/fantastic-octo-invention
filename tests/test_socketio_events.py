"""
Tests for Socket.IO events.
"""

import pytest


class TestSocketIOConnection:
    """Tests for Socket.IO connection events."""

    def test_connect(self, socketio_client, clean_runtime):
        """Client should be able to connect."""
        assert socketio_client.is_connected()

    def test_disconnect(self, socketio_client, clean_runtime):
        """Client should be able to disconnect."""
        socketio_client.disconnect()
        assert not socketio_client.is_connected()


class TestCreateRoom:
    """Tests for room creation."""

    def test_create_room_returns_room_id(self, socketio_client, clean_runtime):
        """Creating a room should return a room ID."""
        socketio_client.emit('create_room', {})
        received = socketio_client.get_received()

        # Find room_created event
        room_created = None
        for event in received:
            if event['name'] == 'room_created':
                room_created = event['args'][0]
                break

        assert room_created is not None
        assert 'room_id' in room_created
        assert len(room_created['room_id']) == 6

    def test_create_room_code_is_uppercase(self, socketio_client, clean_runtime):
        """Room code should be uppercase."""
        socketio_client.emit('create_room', {})
        received = socketio_client.get_received()

        for event in received:
            if event['name'] == 'room_created':
                room_id = event['args'][0]['room_id']
                assert room_id == room_id.upper()
                break


class TestJoinRoom:
    """Tests for joining rooms."""

    def test_join_nonexistent_room_returns_error(self, socketio_client, clean_runtime):
        """Joining a non-existent room should return an error."""
        socketio_client.emit('join_room', {
            'room_id': 'NOTFOUND',
            'player': 1
        })
        received = socketio_client.get_received()

        error = None
        for event in received:
            if event['name'] == 'error':
                error = event['args'][0]
                break

        assert error is not None
        assert 'not found' in error['message'].lower()

    def test_join_room_without_room_id_returns_error(self, socketio_client, clean_runtime):
        """Joining without room_id should return an error."""
        socketio_client.emit('join_room', {
            'player': 1
        })
        received = socketio_client.get_received()

        error = None
        for event in received:
            if event['name'] == 'error':
                error = event['args'][0]
                break

        assert error is not None
        assert 'room_id' in error['message'].lower()

    def test_join_room_invalid_player_returns_error(self, socketio_client, clean_runtime):
        """Joining with invalid player number should return an error."""
        # First create a room
        socketio_client.emit('create_room', {})
        received = socketio_client.get_received()

        room_id = None
        for event in received:
            if event['name'] == 'room_created':
                room_id = event['args'][0]['room_id']
                break

        # Try to join with invalid player
        socketio_client.emit('join_room', {
            'room_id': room_id,
            'player': 3  # Invalid
        })
        received = socketio_client.get_received()

        error = None
        for event in received:
            if event['name'] == 'error':
                error = event['args'][0]
                break

        assert error is not None
        assert 'invalid' in error['message'].lower()

    def test_join_room_successfully(self, socketio_client, clean_runtime):
        """Successfully joining a room should return joined event."""
        # Create room
        socketio_client.emit('create_room', {})
        received = socketio_client.get_received()

        room_id = None
        for event in received:
            if event['name'] == 'room_created':
                room_id = event['args'][0]['room_id']
                break

        # Join room
        socketio_client.emit('join_room', {
            'room_id': room_id,
            'player': 1
        })
        received = socketio_client.get_received()

        joined = None
        for event in received:
            if event['name'] == 'joined':
                joined = event['args'][0]
                break

        assert joined is not None
        assert joined['room_id'] == room_id
        assert joined['player'] == 1
        assert 'token' in joined


class TestSetSecret:
    """Tests for setting secrets."""

    def _create_and_join_room(self, socketio_client):
        """Helper to create and join a room."""
        socketio_client.emit('create_room', {})
        received = socketio_client.get_received()

        room_id = None
        for event in received:
            if event['name'] == 'room_created':
                room_id = event['args'][0]['room_id']
                break

        socketio_client.emit('join_room', {
            'room_id': room_id,
            'player': 1
        })
        socketio_client.get_received()  # Clear receive buffer

        return room_id

    def test_set_valid_secret(self, socketio_client, clean_runtime):
        """Setting a valid secret should succeed."""
        room_id = self._create_and_join_room(socketio_client)

        socketio_client.emit('set_secret', {
            'room_id': room_id,
            'player': 1,
            'secret': '1234'
        })
        received = socketio_client.get_received()

        secret_ack = None
        for event in received:
            if event['name'] == 'secret_ack':
                secret_ack = event['args'][0]
                break

        assert secret_ack is not None
        assert secret_ack['player'] == 1

    def test_set_invalid_secret_too_short(self, socketio_client, clean_runtime):
        """Setting a secret that's too short should fail."""
        room_id = self._create_and_join_room(socketio_client)

        socketio_client.emit('set_secret', {
            'room_id': room_id,
            'player': 1,
            'secret': '123'  # Too short
        })
        received = socketio_client.get_received()

        error = None
        for event in received:
            if event['name'] == 'error':
                error = event['args'][0]
                break

        assert error is not None

    def test_set_invalid_secret_below_min(self, socketio_client, clean_runtime):
        """Setting a secret below minimum should fail."""
        room_id = self._create_and_join_room(socketio_client)

        socketio_client.emit('set_secret', {
            'room_id': room_id,
            'player': 1,
            'secret': '0999'  # Below 1000
        })
        received = socketio_client.get_received()

        error = None
        for event in received:
            if event['name'] == 'error':
                error = event['args'][0]
                break

        assert error is not None


class TestGameFlow:
    """Integration tests for complete game flow."""

    def test_cannot_start_game_without_secrets(self, socketio_client, clean_runtime):
        """Game should not start if secrets aren't set."""
        # Create and join room
        socketio_client.emit('create_room', {})
        received = socketio_client.get_received()

        room_id = None
        for event in received:
            if event['name'] == 'room_created':
                room_id = event['args'][0]['room_id']
                break

        socketio_client.emit('join_room', {
            'room_id': room_id,
            'player': 1
        })
        socketio_client.get_received()

        # Try to start game
        socketio_client.emit('start_game', {'room_id': room_id})
        received = socketio_client.get_received()

        error = None
        for event in received:
            if event['name'] == 'error':
                error = event['args'][0]
                break

        assert error is not None
        assert 'both players' in error['message'].lower()

    def test_cannot_guess_before_game_starts(self, socketio_client, clean_runtime):
        """Should not be able to submit guess before game starts."""
        # Create and join room
        socketio_client.emit('create_room', {})
        received = socketio_client.get_received()

        room_id = None
        for event in received:
            if event['name'] == 'room_created':
                room_id = event['args'][0]['room_id']
                break

        socketio_client.emit('join_room', {
            'room_id': room_id,
            'player': 1
        })
        socketio_client.get_received()

        # Try to guess
        socketio_client.emit('submit_guess', {
            'room_id': room_id,
            'player': 1,
            'guess': '1234'
        })
        received = socketio_client.get_received()

        error = None
        for event in received:
            if event['name'] == 'error':
                error = event['args'][0]
                break

        assert error is not None
        assert 'not started' in error['message'].lower()
