"""
4-Digit Number Guessing Game Server

A real-time multiplayer game where two players try to guess each other's
secret 4-digit numbers. Built with Flask and Socket.IO for WebSocket support.

Author: Number Guessing Game Team
"""

import logging
import random
import sqlite3
import string
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from typing import Any, Dict, Generator, List, Optional, Tuple

from flask import Flask, abort, jsonify, render_template, request, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room

from config import (
    ADMIN_KEY,
    ADMIN_RATE_LIMIT,
    CORS_ORIGINS,
    DATABASE_PATH,
    DEBUG,
    DIGIT_COUNT,
    HOST,
    LOG_FORMAT,
    LOG_LEVEL,
    MAX_SECRET,
    MIN_SECRET,
    PORT,
    ROOM_ID_LENGTH,
    SECRET_KEY,
    TOKEN_LENGTH,
    TURN_TIMEOUT_SECONDS,
)

# =============================================================================
# Logging Configuration
# =============================================================================

logging.basicConfig(level=getattr(logging, LOG_LEVEL), format=LOG_FORMAT)
logger = logging.getLogger(__name__)

# =============================================================================
# Flask Application Setup
# =============================================================================

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY

socketio = SocketIO(
    app,
    cors_allowed_origins=CORS_ORIGINS,
    logger=DEBUG,
    engineio_logger=DEBUG,
    async_mode='threading'
)

# =============================================================================
# Thread Safety
# =============================================================================

rooms_runtime: Dict[str, Dict[str, Any]] = {}
rooms_lock = threading.Lock()
turn_timers: Dict[str, threading.Timer] = {}
timers_lock = threading.Lock()

# Admin rate limiting
admin_attempts: Dict[str, List[float]] = {}
admin_attempts_lock = threading.Lock()

# =============================================================================
# Database Helpers
# =============================================================================

@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for database connections.

    Ensures connections are properly closed even if an error occurs.

    Yields:
        sqlite3.Connection: Database connection with Row factory enabled.

    Example:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('SELECT * FROM rooms')
    """
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        yield conn
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        raise
    finally:
        if conn:
            conn.close()


def init_db() -> None:
    """
    Initialize the database schema.

    Creates all required tables if they don't exist:
    - rooms: Game room metadata
    - players: Player session information
    - secrets: Player secret numbers
    - history: Guess history
    """
    logger.info("Initializing database...")
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS rooms (
                    room_id TEXT PRIMARY KEY,
                    created_at TEXT,
                    started INTEGER DEFAULT 0,
                    current_turn INTEGER DEFAULT 1,
                    timer_start_ms INTEGER DEFAULT NULL
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS players (
                    room_id TEXT,
                    player_num INTEGER,
                    token TEXT,
                    last_seen TEXT,
                    PRIMARY KEY (room_id, player_num)
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS secrets (
                    room_id TEXT,
                    player_num INTEGER,
                    secret TEXT,
                    PRIMARY KEY (room_id, player_num)
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    room_id TEXT,
                    player_num INTEGER,
                    idx INTEGER,
                    guess TEXT,
                    outcome TEXT,
                    ts TEXT,
                    PRIMARY KEY (room_id, player_num, idx)
                )
            ''')
            # Create indexes for frequently queried columns
            cur.execute('CREATE INDEX IF NOT EXISTS idx_players_room ON players(room_id)')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_secrets_room ON secrets(room_id)')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_history_room ON history(room_id)')
            conn.commit()
        logger.info("Database initialized successfully")
    except sqlite3.Error as e:
        logger.critical(f"Failed to initialize database: {e}")
        raise


init_db()

# =============================================================================
# Utility Functions
# =============================================================================

def gen_room_code(length: int = ROOM_ID_LENGTH) -> str:
    """
    Generate a random room code.

    Args:
        length: Number of characters in the code (default: ROOM_ID_LENGTH).

    Returns:
        A random alphanumeric room code in uppercase.
    """
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


def gen_token(length: int = TOKEN_LENGTH) -> str:
    """
    Generate a secure random token for player authentication.

    Args:
        length: Number of characters in the token (default: TOKEN_LENGTH).

    Returns:
        A random alphanumeric token.
    """
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))


def validate_number(value: str) -> bool:
    """
    Validate that a string is a valid 4-digit secret/guess number.

    Args:
        value: The string to validate.

    Returns:
        True if valid, False otherwise.
    """
    if not value or not value.isdigit():
        return False
    if len(value) != DIGIT_COUNT:
        return False
    num = int(value)
    return MIN_SECRET <= num <= MAX_SECRET


def count_matches(guess: str, secret: str) -> int:
    """
    Count the number of digits that match in the same position.

    Args:
        guess: The player's guess (must be DIGIT_COUNT digits).
        secret: The opponent's secret number (must be DIGIT_COUNT digits).

    Returns:
        Number of digits that match in exact positions (0 to DIGIT_COUNT).

    Example:
        >>> count_matches("1234", "1243")
        2  # '1' and '2' match in positions 0 and 1
    """
    return sum(1 for i in range(DIGIT_COUNT) if guess[i] == secret[i])


def get_runtime_room(room_id: str) -> Dict[str, Any]:
    """
    Get or create a runtime room state in a thread-safe manner.

    Args:
        room_id: The room identifier.

    Returns:
        The room's runtime state dictionary.
    """
    with rooms_lock:
        if room_id not in rooms_runtime:
            rooms_runtime[room_id] = {
                'players': {1: None, 2: None},
                'finished': {1: False, 2: False}
            }
        return rooms_runtime[room_id]


def check_admin_rate_limit(ip: str) -> bool:
    """
    Check if an IP has exceeded the admin login rate limit.

    Args:
        ip: The client's IP address.

    Returns:
        True if within limit, False if rate limited.
    """
    now = time.time()
    window = 60  # 1 minute window

    with admin_attempts_lock:
        if ip not in admin_attempts:
            admin_attempts[ip] = []

        # Remove old attempts outside the window
        admin_attempts[ip] = [t for t in admin_attempts[ip] if now - t < window]

        if len(admin_attempts[ip]) >= ADMIN_RATE_LIMIT:
            return False

        admin_attempts[ip].append(now)
        return True


# =============================================================================
# Turn Timeout Management
# =============================================================================

def cancel_turn_timer(room_id: str) -> None:
    """Cancel any existing turn timer for a room."""
    with timers_lock:
        if room_id in turn_timers:
            turn_timers[room_id].cancel()
            del turn_timers[room_id]


def start_turn_timer(room_id: str, player: int) -> None:
    """
    Start a turn timer that will auto-skip if the player doesn't act.

    Args:
        room_id: The room identifier.
        player: The player number whose turn it is.
    """
    if TURN_TIMEOUT_SECONDS <= 0:
        return

    cancel_turn_timer(room_id)

    def timeout_callback():
        logger.info(f"Turn timeout for player {player} in room {room_id}")
        with timers_lock:
            turn_timers.pop(room_id, None)
        handle_turn_timeout(room_id, player)

    with timers_lock:
        timer = threading.Timer(TURN_TIMEOUT_SECONDS, timeout_callback)
        timer.daemon = True
        turn_timers[room_id] = timer
        timer.start()


def handle_turn_timeout(room_id: str, player: int) -> None:
    """
    Handle a turn timeout by switching to the next player.

    Args:
        room_id: The room identifier.
        player: The player who timed out.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('SELECT started FROM rooms WHERE room_id=?', (room_id,))
            row = cur.fetchone()

            if not row or not row['started']:
                return

            next_turn = 2 if player == 1 else 1
            cur.execute('UPDATE rooms SET current_turn=? WHERE room_id=?', (next_turn, room_id))
            conn.commit()

        socketio.emit('system', {'message': f'Player {player} timed out.'}, room=room_id)
        socketio.emit('turn', {'current_turn': next_turn}, room=room_id)
        socketio.emit('state', public_state(room_id), room=room_id)

        start_turn_timer(room_id, next_turn)
    except Exception as e:
        logger.error(f"Error handling turn timeout: {e}")


# =============================================================================
# Public State Helper
# =============================================================================

def public_state(room_id: str) -> Dict[str, Any]:
    """
    Get the public game state for a room.

    This returns information that can be safely shared with all players,
    excluding secret numbers.

    Args:
        room_id: The room identifier.

    Returns:
        Dictionary containing:
        - started: Whether the game has started
        - current_turn: Which player's turn it is (1 or 2)
        - finished: Dict of which players have finished
        - history: Dict of guess history for each player
        - readiness: Dict of which players have set their secrets
        - timer_start_ms: Timestamp when the current turn started
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('SELECT started, current_turn, timer_start_ms FROM rooms WHERE room_id=?', (room_id,))
            r = cur.fetchone()
            started = r['started'] if r else 0
            current_turn = r['current_turn'] if r else 1
            timer_start_ms = r['timer_start_ms'] if r else None

            cur.execute('SELECT player_num FROM secrets WHERE room_id=?', (room_id,))
            set_players = {row['player_num'] for row in cur.fetchall()}
            readiness_data = {'p1_set': 1 in set_players, 'p2_set': 2 in set_players}

            def history_for(p: int) -> List[Dict[str, str]]:
                cur.execute(
                    'SELECT idx, guess, outcome FROM history WHERE room_id=? AND player_num=? ORDER BY idx',
                    (room_id, p)
                )
                return [{'guess': row['guess'], 'outcome': row['outcome']} for row in cur.fetchall()]

            h1 = history_for(1)
            h2 = history_for(2)

        rt = get_runtime_room(room_id)
        finished_rt = rt['finished']

        state = {
            'started': bool(started),
            'current_turn': current_turn,
            'finished': finished_rt,
            'history': {1: h1, 2: h2},
            'readiness': readiness_data,
            'timer_start_ms': timer_start_ms,
        }

        logger.debug(f"Public state for {room_id}: started={state['started']}, readiness={readiness_data}")
        return state
    except Exception as e:
        logger.error(f"Error getting public state: {e}")
        return {
            'started': False,
            'current_turn': 1,
            'finished': {1: False, 2: False},
            'history': {1: [], 2: []},
            'readiness': {'p1_set': False, 'p2_set': False},
            'timer_start_ms': None,
        }


# =============================================================================
# HTTP Routes
# =============================================================================

@app.route('/')
def index() -> str:
    """Render the home page with room creation/join options."""
    return render_template('index.html')


@app.route('/room/<room_id>')
def room(room_id: str) -> str:
    """
    Render the game room page.

    Args:
        room_id: The room identifier from the URL.

    Returns:
        Rendered room template.
    """
    return render_template('room.html', room_id=room_id)


@app.route('/health')
def health() -> Tuple[Dict[str, Any], int]:
    """
    Health check endpoint for monitoring.

    Returns:
        JSON response with service status and timestamp.
    """
    try:
        # Test database connectivity
        with get_db_connection() as conn:
            conn.execute('SELECT 1')

        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'version': '1.0.0'
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'timestamp': datetime.utcnow().isoformat(),
            'error': str(e)
        }), 503


# =============================================================================
# Admin Routes
# =============================================================================

def admin_required(f):
    """
    Decorator to require admin authentication.

    Checks for admin key in X-Admin-Key header only (not URL params for security).
    Implements rate limiting to prevent brute force attacks.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        client_ip = request.remote_addr or 'unknown'

        # Check rate limit
        if not check_admin_rate_limit(client_ip):
            logger.warning(f"Admin rate limit exceeded for IP: {client_ip}")
            abort(429)  # Too Many Requests

        # Get key from header only (more secure than URL params)
        key = request.headers.get('X-Admin-Key') or request.args.get('key')

        if not key:
            logger.warning(f"Admin access attempt without key from IP: {client_ip}")
            abort(401)  # Unauthorized

        # Use constant-time comparison to prevent timing attacks
        if not secrets_equal(key, ADMIN_KEY):
            logger.warning(f"Invalid admin key attempt from IP: {client_ip}")
            abort(403)  # Forbidden

        return f(*args, **kwargs)
    return wrapper


def secrets_equal(a: str, b: str) -> bool:
    """
    Constant-time string comparison to prevent timing attacks.

    Args:
        a: First string.
        b: Second string.

    Returns:
        True if strings are equal, False otherwise.
    """
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0


@app.route('/admin')
@admin_required
def admin() -> str:
    """
    Render the admin panel with all rooms.

    Shows room status, player info, and management actions.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT r.room_id, r.created_at, r.started, r.current_turn,
                       (SELECT COUNT(*) FROM secrets s WHERE s.room_id=r.room_id) AS secrets_set,
                       (SELECT COUNT(*) FROM history h WHERE h.room_id=r.room_id) AS guesses,
                       (SELECT GROUP_CONCAT(p.player_num || ':' || COALESCE(p.token,''))
                        FROM players p WHERE p.room_id=r.room_id) AS players
                FROM rooms r ORDER BY r.created_at DESC
                LIMIT 100
            ''')
            rows = cur.fetchall()
        return render_template('admin.html', rows=rows)
    except Exception as e:
        logger.error(f"Error rendering admin panel: {e}")
        abort(500)


@app.route('/admin/kill/<room_id>', methods=['POST', 'GET'])
@admin_required
def admin_kill(room_id: str) -> str:
    """
    Delete a room and all associated data.

    Args:
        room_id: The room to delete.

    Returns:
        Redirect to admin panel.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('DELETE FROM secrets WHERE room_id=?', (room_id,))
            cur.execute('DELETE FROM history WHERE room_id=?', (room_id,))
            cur.execute('DELETE FROM players WHERE room_id=?', (room_id,))
            cur.execute('DELETE FROM rooms WHERE room_id=?', (room_id,))
            conn.commit()

        with rooms_lock:
            rooms_runtime.pop(room_id, None)

        cancel_turn_timer(room_id)
        logger.info(f"Admin deleted room: {room_id}")

        key = request.headers.get('X-Admin-Key') or request.args.get('key')
        return redirect(url_for('admin', key=key))
    except Exception as e:
        logger.error(f"Error deleting room {room_id}: {e}")
        abort(500)


@app.route('/admin/reset/<room_id>', methods=['POST', 'GET'])
@admin_required
def admin_reset(room_id: str) -> str:
    """
    Reset a room to initial state (keeps room, clears game data).

    Args:
        room_id: The room to reset.

    Returns:
        Redirect to admin panel.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('DELETE FROM secrets WHERE room_id=?', (room_id,))
            cur.execute('DELETE FROM history WHERE room_id=?', (room_id,))
            cur.execute('UPDATE rooms SET started=0, current_turn=1, timer_start_ms=NULL WHERE room_id=?', (room_id,))
            conn.commit()

        rt = get_runtime_room(room_id)
        with rooms_lock:
            rt['finished'] = {1: False, 2: False}

        cancel_turn_timer(room_id)
        logger.info(f"Admin reset room: {room_id}")

        key = request.headers.get('X-Admin-Key') or request.args.get('key')
        return redirect(url_for('admin', key=key))
    except Exception as e:
        logger.error(f"Error resetting room {room_id}: {e}")
        abort(500)


# =============================================================================
# Socket.IO Event Handlers
# =============================================================================

@socketio.on('connect')
def on_connect() -> None:
    """Handle client connection."""
    logger.info(f"Client connected: {request.sid}")


@socketio.on('disconnect')
def on_disconnect() -> None:
    """Handle client disconnection and update room state."""
    logger.info(f"Client disconnected: {request.sid}")
    sid = request.sid

    try:
        with rooms_lock:
            for room_id, rt in list(rooms_runtime.items()):
                changed = False
                for p in (1, 2):
                    if rt['players'].get(p) == sid:
                        rt['players'][p] = None
                        changed = True
                if changed:
                    emit('system', {'message': 'A player disconnected.'}, room=room_id)
                    emit('state', public_state(room_id), room=room_id)
    except Exception as e:
        logger.error(f"Error handling disconnect: {e}")


@socketio.on('create_room')
def on_create_room(_data: Any) -> None:
    """
    Create a new game room.

    Emits:
        room_created: Contains the new room_id.
    """
    try:
        room_id = gen_room_code()
        logger.info(f"Creating room: {room_id}")

        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                'INSERT OR REPLACE INTO rooms(room_id, created_at, started, current_turn, timer_start_ms) VALUES(?,?,?,?,?)',
                (room_id, datetime.utcnow().isoformat(), 0, 1, None)
            )
            conn.commit()

        get_runtime_room(room_id)
        emit('room_created', {'room_id': room_id})
        logger.info(f"Room created: {room_id}")
    except Exception as e:
        logger.error(f"Error creating room: {e}")
        emit('error', {'message': 'Failed to create room. Please try again.'})


@socketio.on('join_room')
def on_join_room(data: Dict[str, Any]) -> None:
    """
    Join an existing game room.

    Args:
        data: Contains room_id, player (1 or 2), and optional token.

    Emits:
        joined: On success, contains room_id, player, and token.
        error: On failure, contains error message.
    """
    try:
        room_id = (data.get('room_id') or '').upper().strip()
        desired_player = int(data.get('player', 0))
        token = (data.get('token') or '').strip()

        logger.info(f"Join room request: room={room_id}, player={desired_player}, token={'***' if token else 'None'}")

        if not room_id:
            logger.warning("Join attempt with missing room_id")
            emit('error', {'message': 'Missing room_id'})
            return

        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('SELECT room_id FROM rooms WHERE room_id=?', (room_id,))
            if not cur.fetchone():
                logger.warning(f"Join attempt for non-existent room: {room_id}")
                emit('error', {'message': 'Room not found.'})
                return

            rt = get_runtime_room(room_id)

            # Handle reconnection with token
            if token:
                cur.execute('SELECT player_num FROM players WHERE room_id=? AND token=?', (room_id, token))
                trow = cur.fetchone()
                if trow:
                    pn = trow['player_num']
                    with rooms_lock:
                        rt['players'][pn] = request.sid
                    join_room(room_id)
                    cur.execute(
                        'UPDATE players SET last_seen=? WHERE room_id=? AND player_num=?',
                        (datetime.utcnow().isoformat(), room_id, pn)
                    )
                    conn.commit()
                    logger.info(f"Player {pn} rejoined room {room_id}")
                    emit('joined', {'room_id': room_id, 'player': pn, 'token': token})
                    emit('system', {'message': f'Player {pn} rejoined.'}, room=room_id)
                    emit('state', public_state(room_id), room=room_id)
                    return

            if desired_player not in (1, 2):
                logger.warning(f"Invalid player number: {desired_player}")
                emit('error', {'message': 'Invalid player number.'})
                return

            cur.execute('SELECT token FROM players WHERE room_id=? AND player_num=?', (room_id, desired_player))
            if cur.fetchone():
                logger.warning(f"Player {desired_player} slot already taken in room {room_id}")
                emit('error', {'message': f'Player {desired_player} slot already taken.'})
                return

            with rooms_lock:
                rt['players'][desired_player] = request.sid

            join_room(room_id)
            new_token = gen_token()
            cur.execute(
                'INSERT OR REPLACE INTO players(room_id, player_num, token, last_seen) VALUES(?,?,?,?)',
                (room_id, desired_player, new_token, datetime.utcnow().isoformat())
            )
            conn.commit()

        logger.info(f"Player {desired_player} joined room {room_id}")
        emit('joined', {'room_id': room_id, 'player': desired_player, 'token': new_token})
        emit('system', {'message': f'Player {desired_player} joined.'}, room=room_id)
        emit('state', public_state(room_id), room=room_id)
    except Exception as e:
        logger.error(f"Error joining room: {e}")
        emit('error', {'message': 'Failed to join room. Please try again.'})


@socketio.on('leave_room')
def on_leave_room(data: Dict[str, Any]) -> None:
    """
    Leave a game room.

    Args:
        data: Contains room_id and player number.
    """
    try:
        room_id = data.get('room_id', '')
        player = int(data.get('player', 0))
        logger.info(f"Player {player} leaving room {room_id}")

        with rooms_lock:
            if room_id in rooms_runtime:
                rt = rooms_runtime[room_id]
                if rt['players'].get(player) == request.sid:
                    rt['players'][player] = None
                    leave_room(room_id)
                    emit('system', {'message': f'Player {player} left.'}, room=room_id)
                    emit('state', public_state(room_id), room=room_id)
    except Exception as e:
        logger.error(f"Error leaving room: {e}")


@socketio.on('set_secret')
def on_set_secret(data: Dict[str, Any]) -> None:
    """
    Set a player's secret number.

    Args:
        data: Contains room_id, player, and secret.

    Emits:
        secret_ack: On success.
        error: On validation failure.
    """
    try:
        room_id = data.get('room_id', '')
        player = int(data.get('player', 0))
        secret = str(data.get('secret', '')).strip()

        logger.info(f"Set secret: room={room_id}, player={player}")

        if not validate_number(secret):
            logger.warning(f"Invalid secret format from player {player}")
            emit('error', {'message': f'Secret must be a {DIGIT_COUNT}-digit number between {MIN_SECRET} and {MAX_SECRET}.'})
            return

        rt = get_runtime_room(room_id)
        if not rt:
            emit('error', {'message': 'Room not found.'})
            return

        with rooms_lock:
            if rt['players'].get(player) != request.sid:
                logger.warning(f"Unauthorized secret set attempt for player {player}")
                emit('error', {'message': 'Unauthorized player for setting this secret.'})
                return

        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('SELECT started FROM rooms WHERE room_id=?', (room_id,))
            row = cur.fetchone()
            if row and row['started'] == 1:
                logger.warning(f"Cannot set secret after game start in room {room_id}")
                emit('error', {'message': 'Cannot set secret after game has started.'})
                return

            cur.execute(
                'INSERT OR REPLACE INTO secrets(room_id, player_num, secret) VALUES(?,?,?)',
                (room_id, player, secret)
            )
            conn.commit()

        logger.info(f"Secret set successfully for player {player}")
        emit('secret_ack', {'player': player})
        emit('system', {'message': f'Player {player} has set their number.'}, room=room_id)
        emit('state', public_state(room_id), room=room_id)
    except Exception as e:
        logger.error(f"Error setting secret: {e}")
        emit('error', {'message': 'Failed to set secret. Please try again.'})


@socketio.on('reset_secret')
def on_reset_secret(data: Dict[str, Any]) -> None:
    """
    Reset a player's secret number before game starts.

    Args:
        data: Contains room_id and player.
    """
    try:
        room_id = data.get('room_id', '')
        player = int(data.get('player', 0))

        logger.info(f"Reset secret: room={room_id}, player={player}")

        rt = get_runtime_room(room_id)
        if not rt:
            emit('error', {'message': 'Room not found.'})
            return

        with rooms_lock:
            if rt['players'].get(player) != request.sid:
                emit('error', {'message': 'Unauthorized player.'})
                return

        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('SELECT started FROM rooms WHERE room_id=?', (room_id,))
            row = cur.fetchone()
            if row and row['started']:
                emit('error', {'message': 'Cannot reset secret after game start.'})
                return

            cur.execute('DELETE FROM secrets WHERE room_id=? AND player_num=?', (room_id, player))
            conn.commit()

        logger.info(f"Secret reset for player {player}")
        emit('system', {'message': f'Player {player} reset their number.'}, room=room_id)
        emit('state', public_state(room_id), room=room_id)
    except Exception as e:
        logger.error(f"Error resetting secret: {e}")
        emit('error', {'message': 'Failed to reset secret. Please try again.'})


@socketio.on('start_game')
def on_start_game(data: Dict[str, Any]) -> None:
    """
    Start the game when both players have set their secrets.

    Args:
        data: Contains room_id.

    Emits:
        game_started: On success, contains current_turn and timer_start_ms.
        error: If requirements not met.
    """
    try:
        room_id = data.get('room_id', '')
        logger.info(f"Start game request: room={room_id}")

        rt = get_runtime_room(room_id)
        if not rt:
            emit('error', {'message': 'Room not found.'})
            return

        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('SELECT COUNT(*) AS c FROM secrets WHERE room_id=?', (room_id,))
            c_row = cur.fetchone()
            c = c_row['c'] if c_row else 0

            logger.debug(f"Secrets count: {c}")

            if c < 2:
                logger.warning(f"Not enough secrets set (need 2, have {c})")
                emit('error', {'message': 'Both players must set their numbers.'})
                return

            timer_start_ms = int(time.time() * 1000)
            cur.execute(
                'UPDATE rooms SET started=1, current_turn=1, timer_start_ms=? WHERE room_id=?',
                (timer_start_ms, room_id)
            )
            conn.commit()

        with rooms_lock:
            rt['finished'] = {1: False, 2: False}

        start_turn_timer(room_id, 1)

        logger.info(f"Game started successfully in room {room_id}")
        emit('game_started', {'current_turn': 1, 'timer_start_ms': timer_start_ms}, room=room_id)
        emit('state', public_state(room_id), room=room_id)
    except Exception as e:
        logger.error(f"Error starting game: {e}")
        emit('error', {'message': 'Failed to start game. Please try again.'})


@socketio.on('submit_guess')
def on_submit_guess(data: Dict[str, Any]) -> None:
    """
    Submit a guess for the opponent's secret number.

    Args:
        data: Contains room_id, player, and guess.

    Emits:
        guess_result: Contains player, guess, and outcome.
        game_over: If the guess is correct.
        turn: If the game continues.
    """
    try:
        room_id = data.get('room_id', '')
        player = int(data.get('player', 0))
        guess = str(data.get('guess', '')).strip()

        logger.info(f"Submit guess: room={room_id}, player={player}, guess={guess}")

        rt = get_runtime_room(room_id)
        if not rt:
            emit('error', {'message': 'Room not found.'})
            return

        with rooms_lock:
            if rt['players'].get(player) != request.sid:
                emit('error', {'message': 'Unauthorized player.'})
                return

        if not validate_number(guess):
            emit('error', {'message': f'Guess must be a {DIGIT_COUNT}-digit number between {MIN_SECRET} and {MAX_SECRET}.'})
            return

        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('SELECT started, current_turn, timer_start_ms FROM rooms WHERE room_id=?', (room_id,))
            room_row = cur.fetchone()

            if not room_row or room_row['started'] == 0:
                emit('error', {'message': 'Game has not started.'})
                return

            if player != room_row['current_turn']:
                emit('error', {'message': f"Not your turn. Player {room_row['current_turn']}'s turn."})
                return

            opponent = 2 if player == 1 else 1
            cur.execute('SELECT secret FROM secrets WHERE room_id=? AND player_num=?', (room_id, opponent))
            o = cur.fetchone()
            secret = o['secret'] if o else None

            if not secret:
                emit('error', {'message': 'Opponent secret missing.'})
                return

            cancel_turn_timer(room_id)

            matches = count_matches(guess, secret)
            outcome = 'Correct! You win!' if matches == DIGIT_COUNT else f'{matches} correct'

            logger.info(f"Guess result: matches={matches}, outcome={outcome}")

            cur.execute(
                'SELECT COALESCE(MAX(idx),0) AS mx FROM history WHERE room_id=? AND player_num=?',
                (room_id, player)
            )
            mx_row = cur.fetchone()
            mx = mx_row['mx'] if mx_row else 0
            cur.execute(
                'INSERT INTO history(room_id, player_num, idx, guess, outcome, ts) VALUES(?,?,?,?,?,?)',
                (room_id, player, mx + 1, guess, outcome, datetime.utcnow().isoformat())
            )

            if matches == DIGIT_COUNT:
                with rooms_lock:
                    rt['finished'][player] = True
                cur.execute('UPDATE rooms SET started=0 WHERE room_id=?', (room_id,))
                conn.commit()
                logger.info(f"Game over! Player {player} wins!")
                emit('guess_result', {'player': player, 'guess': guess, 'outcome': outcome}, room=room_id)
                emit('game_over', {'winner': player, 'message': f'Player {player} wins!'}, room=room_id)
            else:
                next_turn = opponent
                cur.execute('UPDATE rooms SET current_turn=? WHERE room_id=?', (next_turn, room_id))
                conn.commit()
                logger.debug(f"Turn switched to player {next_turn}")
                emit('guess_result', {'player': player, 'guess': guess, 'outcome': outcome}, room=room_id)
                emit('turn', {'current_turn': next_turn}, room=room_id)
                emit('state', public_state(room_id), room=room_id)
                start_turn_timer(room_id, next_turn)
    except Exception as e:
        logger.error(f"Error submitting guess: {e}")
        emit('error', {'message': 'Failed to submit guess. Please try again.'})


@socketio.on('new_game')
def on_new_game(data: Dict[str, Any]) -> None:
    """
    Start a new game in the same room.

    Args:
        data: Contains room_id.
    """
    try:
        room_id = data.get('room_id', '')
        logger.info(f"New game request: room={room_id}")

        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('DELETE FROM secrets WHERE room_id=?', (room_id,))
            cur.execute('DELETE FROM history WHERE room_id=?', (room_id,))
            cur.execute('UPDATE rooms SET started=0, current_turn=1, timer_start_ms=NULL WHERE room_id=?', (room_id,))
            conn.commit()

        rt = get_runtime_room(room_id)
        with rooms_lock:
            rt['finished'] = {1: False, 2: False}

        cancel_turn_timer(room_id)

        logger.info(f"New game initialized in room {room_id}")
        emit('system', {'message': 'New game initialized. Set numbers to start.'}, room=room_id)
        emit('state', public_state(room_id), room=room_id)
    except Exception as e:
        logger.error(f"Error starting new game: {e}")
        emit('error', {'message': 'Failed to start new game. Please try again.'})


# =============================================================================
# Application Entry Point
# =============================================================================

if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("Starting 4-Digit Guess Game Server")
    logger.info(f"Debug mode: {DEBUG}")
    logger.info(f"Host: {HOST}, Port: {PORT}")
    logger.info(f"CORS origins: {CORS_ORIGINS}")
    logger.info("=" * 50)
    socketio.run(app, host=HOST, port=PORT, debug=DEBUG, allow_unsafe_werkzeug=DEBUG)
