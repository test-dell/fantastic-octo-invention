"""
4-Digit Number Guessing Game Server

A real-time multiplayer game where two players try to guess each other's
secret 4-digit numbers. Built with Flask and Socket.IO for WebSocket support.
"""

import logging
import random
import sqlite3
import string
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Generator, List, Tuple

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room

from config import (
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
    ROOM_INACTIVITY_TIMEOUT_SECONDS,
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
room_inactivity_timers: Dict[str, threading.Timer] = {}
inactivity_timers_lock = threading.Lock()

# =============================================================================
# Database Helpers
# =============================================================================


@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database connections."""
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
    """Initialize the database schema."""
    logger.info("Initializing database...")
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS rooms (
                    room_id TEXT PRIMARY KEY,
                    created_at TEXT,
                    last_activity TEXT,
                    started INTEGER DEFAULT 0,
                    current_turn INTEGER DEFAULT 1,
                    timer_start_ms INTEGER DEFAULT NULL
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS players (
                    room_id TEXT,
                    player_num INTEGER,
                    player_name TEXT,
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
    """Generate a random room code."""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


def gen_token(length: int = TOKEN_LENGTH) -> str:
    """Generate a secure random token for player authentication."""
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))


def validate_number(value: str) -> bool:
    """Validate that a string is a valid 4-digit secret/guess number."""
    if not value or not value.isdigit():
        return False
    if len(value) != DIGIT_COUNT:
        return False
    num = int(value)
    return MIN_SECRET <= num <= MAX_SECRET


def count_matches(guess: str, secret: str) -> int:
    """Count the number of digits that match in the same position."""
    return sum(1 for i in range(DIGIT_COUNT) if guess[i] == secret[i])


def get_runtime_room(room_id: str) -> Dict[str, Any]:
    """Get or create a runtime room state in a thread-safe manner."""
    with rooms_lock:
        if room_id not in rooms_runtime:
            rooms_runtime[room_id] = {
                'players': {1: None, 2: None},
                'player_names': {1: 'Player 1', 2: 'Player 2'},
                'finished': {1: False, 2: False}
            }
        return rooms_runtime[room_id]


def update_room_activity(room_id: str) -> None:
    """Update the last activity timestamp for a room and reset inactivity timer."""
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                'UPDATE rooms SET last_activity=? WHERE room_id=?',
                (datetime.utcnow().isoformat(), room_id)
            )
            conn.commit()
        start_room_inactivity_timer(room_id)
    except Exception as e:
        logger.error(f"Error updating room activity: {e}")


# =============================================================================
# Room Inactivity Timeout Management
# =============================================================================


def cancel_room_inactivity_timer(room_id: str) -> None:
    """Cancel any existing inactivity timer for a room."""
    with inactivity_timers_lock:
        if room_id in room_inactivity_timers:
            room_inactivity_timers[room_id].cancel()
            del room_inactivity_timers[room_id]


def start_room_inactivity_timer(room_id: str) -> None:
    """Start an inactivity timer that will abort the room after timeout."""
    if ROOM_INACTIVITY_TIMEOUT_SECONDS <= 0:
        return

    cancel_room_inactivity_timer(room_id)

    def timeout_callback():
        logger.info(f"Room {room_id} timed out due to inactivity")
        with inactivity_timers_lock:
            room_inactivity_timers.pop(room_id, None)
        handle_room_inactivity_timeout(room_id)

    with inactivity_timers_lock:
        timer = threading.Timer(ROOM_INACTIVITY_TIMEOUT_SECONDS, timeout_callback)
        timer.daemon = True
        room_inactivity_timers[room_id] = timer
        timer.start()


def handle_room_inactivity_timeout(room_id: str) -> None:
    """Handle room inactivity timeout by notifying players and cleaning up."""
    try:
        socketio.emit('room_expired', {
            'message': 'Room closed due to 20 minutes of inactivity.'
        }, room=room_id)

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
        logger.info(f"Room {room_id} cleaned up after inactivity timeout")
    except Exception as e:
        logger.error(f"Error handling room inactivity timeout: {e}")


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
    """Start a turn timer that will auto-skip if the player doesn't act."""
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
    """Handle a turn timeout by switching to the next player."""
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

        rt = get_runtime_room(room_id)
        player_name = rt['player_names'].get(player, f'Player {player}')
        socketio.emit('system', {'message': f'{player_name} timed out.'}, room=room_id)
        socketio.emit('turn', {'current_turn': next_turn}, room=room_id)
        socketio.emit('state', public_state(room_id), room=room_id)

        start_turn_timer(room_id, next_turn)
        update_room_activity(room_id)
    except Exception as e:
        logger.error(f"Error handling turn timeout: {e}")


# =============================================================================
# Public State Helper
# =============================================================================


def public_state(room_id: str) -> Dict[str, Any]:
    """Get the public game state for a room."""
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

            cur.execute('SELECT player_num, player_name FROM players WHERE room_id=?', (room_id,))
            player_names = {}
            for row in cur.fetchall():
                player_names[row['player_num']] = row['player_name'] or f"Player {row['player_num']}"

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

        for pn, name in player_names.items():
            rt['player_names'][pn] = name

        state = {
            'started': bool(started),
            'current_turn': current_turn,
            'finished': finished_rt,
            'history': {1: h1, 2: h2},
            'readiness': readiness_data,
            'timer_start_ms': timer_start_ms,
            'player_names': rt['player_names'],
        }

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
            'player_names': {1: 'Player 1', 2: 'Player 2'},
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
    """Render the game room page."""
    return render_template('room.html', room_id=room_id)


@app.route('/health')
def health() -> Tuple[Dict[str, Any], int]:
    """Health check endpoint for monitoring."""
    try:
        with get_db_connection() as conn:
            conn.execute('SELECT 1')

        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'version': '2.0.0'
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'timestamp': datetime.utcnow().isoformat(),
            'error': str(e)
        }), 503


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
                player_name = None
                for p in (1, 2):
                    if rt['players'].get(p) == sid:
                        rt['players'][p] = None
                        player_name = rt['player_names'].get(p, f'Player {p}')
                        changed = True
                if changed:
                    emit('system', {'message': f'{player_name} disconnected.'}, room=room_id)
                    emit('state', public_state(room_id), room=room_id)
    except Exception as e:
        logger.error(f"Error handling disconnect: {e}")


@socketio.on('create_room')
def on_create_room(_data: Any) -> None:
    """Create a new game room."""
    try:
        room_id = gen_room_code()
        logger.info(f"Creating room: {room_id}")

        with get_db_connection() as conn:
            cur = conn.cursor()
            now = datetime.utcnow().isoformat()
            cur.execute(
                '''INSERT OR REPLACE INTO rooms
                   (room_id, created_at, last_activity, started, current_turn, timer_start_ms)
                   VALUES(?,?,?,?,?,?)''',
                (room_id, now, now, 0, 1, None)
            )
            conn.commit()

        get_runtime_room(room_id)
        start_room_inactivity_timer(room_id)
        emit('room_created', {'room_id': room_id})
        logger.info(f"Room created: {room_id}")
    except Exception as e:
        logger.error(f"Error creating room: {e}")
        emit('error', {'message': 'Failed to create room. Please try again.'})


@socketio.on('join_room')
def on_join_room(data: Dict[str, Any]) -> None:
    """Join an existing game room."""
    try:
        room_id = (data.get('room_id') or '').upper().strip()
        desired_player = int(data.get('player', 0))
        token = (data.get('token') or '').strip()
        player_name = (data.get('player_name') or '').strip()

        logger.info(f"Join room request: room={room_id}, player={desired_player}, name={player_name}")

        if not room_id:
            emit('error', {'message': 'Missing room_id'})
            return

        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('SELECT room_id FROM rooms WHERE room_id=?', (room_id,))
            if not cur.fetchone():
                emit('error', {'message': 'Room not found.'})
                return

            rt = get_runtime_room(room_id)

            if token:
                cur.execute('SELECT player_num, player_name FROM players WHERE room_id=? AND token=?', (room_id, token))
                trow = cur.fetchone()
                if trow:
                    pn = trow['player_num']
                    stored_name = trow['player_name'] or f'Player {pn}'
                    with rooms_lock:
                        rt['players'][pn] = request.sid
                        rt['player_names'][pn] = stored_name
                    join_room(room_id)
                    cur.execute(
                        'UPDATE players SET last_seen=? WHERE room_id=? AND player_num=?',
                        (datetime.utcnow().isoformat(), room_id, pn)
                    )
                    conn.commit()
                    update_room_activity(room_id)
                    emit('joined', {'room_id': room_id, 'player': pn, 'token': token, 'player_name': stored_name})
                    emit('system', {'message': f'{stored_name} rejoined.'}, room=room_id)
                    emit('state', public_state(room_id), room=room_id)
                    return

            if desired_player not in (1, 2):
                emit('error', {'message': 'Invalid player number.'})
                return

            cur.execute('SELECT token FROM players WHERE room_id=? AND player_num=?', (room_id, desired_player))
            if cur.fetchone():
                emit('error', {'message': f'Player {desired_player} slot already taken.'})
                return

            final_name = player_name if player_name else f'Player {desired_player}'

            with rooms_lock:
                rt['players'][desired_player] = request.sid
                rt['player_names'][desired_player] = final_name

            join_room(room_id)
            new_token = gen_token()
            cur.execute(
                'INSERT OR REPLACE INTO players(room_id, player_num, player_name, token, last_seen) VALUES(?,?,?,?,?)',
                (room_id, desired_player, final_name, new_token, datetime.utcnow().isoformat())
            )
            conn.commit()

        update_room_activity(room_id)
        emit('joined', {'room_id': room_id, 'player': desired_player, 'token': new_token, 'player_name': final_name})
        emit('system', {'message': f'{final_name} joined.'}, room=room_id)
        emit('state', public_state(room_id), room=room_id)
    except Exception as e:
        logger.error(f"Error joining room: {e}")
        emit('error', {'message': 'Failed to join room. Please try again.'})


@socketio.on('leave_room')
def on_leave_room(data: Dict[str, Any]) -> None:
    """Leave a game room."""
    try:
        room_id = data.get('room_id', '')
        player = int(data.get('player', 0))

        with rooms_lock:
            if room_id in rooms_runtime:
                rt = rooms_runtime[room_id]
                if rt['players'].get(player) == request.sid:
                    rt['players'][player] = None
                    player_name = rt['player_names'].get(player, f'Player {player}')
                    leave_room(room_id)
                    emit('system', {'message': f'{player_name} left.'}, room=room_id)
                    emit('state', public_state(room_id), room=room_id)
    except Exception as e:
        logger.error(f"Error leaving room: {e}")


@socketio.on('set_secret')
def on_set_secret(data: Dict[str, Any]) -> None:
    """Set a player's secret number."""
    try:
        room_id = data.get('room_id', '')
        player = int(data.get('player', 0))
        secret = str(data.get('secret', '')).strip()

        if not validate_number(secret):
            msg = f'Secret must be a {DIGIT_COUNT}-digit number between {MIN_SECRET} and {MAX_SECRET}.'
            emit('error', {'message': msg})
            return

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
            if row and row['started'] == 1:
                emit('error', {'message': 'Cannot set secret after game has started.'})
                return

            cur.execute(
                'INSERT OR REPLACE INTO secrets(room_id, player_num, secret) VALUES(?,?,?)',
                (room_id, player, secret)
            )
            conn.commit()

        update_room_activity(room_id)
        player_name = rt['player_names'].get(player, f'Player {player}')
        emit('secret_ack', {'player': player})
        emit('system', {'message': f'{player_name} has set their number.'}, room=room_id)
        emit('state', public_state(room_id), room=room_id)
    except Exception as e:
        logger.error(f"Error setting secret: {e}")
        emit('error', {'message': 'Failed to set secret. Please try again.'})


@socketio.on('reset_secret')
def on_reset_secret(data: Dict[str, Any]) -> None:
    """Reset a player's secret number before game starts."""
    try:
        room_id = data.get('room_id', '')
        player = int(data.get('player', 0))

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

        update_room_activity(room_id)
        player_name = rt['player_names'].get(player, f'Player {player}')
        emit('secret_reset_ack', {'player': player})
        emit('system', {'message': f'{player_name} reset their number.'}, room=room_id)
        emit('state', public_state(room_id), room=room_id)
    except Exception as e:
        logger.error(f"Error resetting secret: {e}")
        emit('error', {'message': 'Failed to reset secret. Please try again.'})


@socketio.on('start_game')
def on_start_game(data: Dict[str, Any]) -> None:
    """Start the game when both players have set their secrets."""
    try:
        room_id = data.get('room_id', '')

        rt = get_runtime_room(room_id)
        if not rt:
            emit('error', {'message': 'Room not found.'})
            return

        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('SELECT COUNT(*) AS c FROM secrets WHERE room_id=?', (room_id,))
            c_row = cur.fetchone()
            c = c_row['c'] if c_row else 0

            if c < 2:
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
        update_room_activity(room_id)

        emit('game_started', {'current_turn': 1, 'timer_start_ms': timer_start_ms}, room=room_id)
        emit('state', public_state(room_id), room=room_id)
    except Exception as e:
        logger.error(f"Error starting game: {e}")
        emit('error', {'message': 'Failed to start game. Please try again.'})


@socketio.on('submit_guess')
def on_submit_guess(data: Dict[str, Any]) -> None:
    """Submit a guess for the opponent's secret number."""
    try:
        room_id = data.get('room_id', '')
        player = int(data.get('player', 0))
        guess = str(data.get('guess', '')).strip()

        rt = get_runtime_room(room_id)
        if not rt:
            emit('error', {'message': 'Room not found.'})
            return

        with rooms_lock:
            if rt['players'].get(player) != request.sid:
                emit('error', {'message': 'Unauthorized player.'})
                return

        if not validate_number(guess):
            msg = f'Guess must be a {DIGIT_COUNT}-digit number between {MIN_SECRET} and {MAX_SECRET}.'
            emit('error', {'message': msg})
            return

        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('SELECT started, current_turn FROM rooms WHERE room_id=?', (room_id,))
            room_row = cur.fetchone()

            if not room_row or room_row['started'] == 0:
                emit('error', {'message': 'Game has not started.'})
                return

            if player != room_row['current_turn']:
                emit('error', {'message': "Not your turn."})
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

            player_name = rt['player_names'].get(player, f'Player {player}')

            if matches == DIGIT_COUNT:
                with rooms_lock:
                    rt['finished'][player] = True
                cur.execute('UPDATE rooms SET started=0 WHERE room_id=?', (room_id,))
                conn.commit()
                emit('guess_result', {'player': player, 'guess': guess, 'outcome': outcome}, room=room_id)
                game_over_data = {
                    'winner': player,
                    'winner_name': player_name,
                    'message': f'{player_name} wins!'
                }
                emit('game_over', game_over_data, room=room_id)
            else:
                next_turn = opponent
                cur.execute('UPDATE rooms SET current_turn=? WHERE room_id=?', (next_turn, room_id))
                conn.commit()
                emit('guess_result', {'player': player, 'guess': guess, 'outcome': outcome}, room=room_id)
                emit('turn', {'current_turn': next_turn}, room=room_id)
                emit('state', public_state(room_id), room=room_id)
                start_turn_timer(room_id, next_turn)

        update_room_activity(room_id)
    except Exception as e:
        logger.error(f"Error submitting guess: {e}")
        emit('error', {'message': 'Failed to submit guess. Please try again.'})


@socketio.on('new_game')
def on_new_game(data: Dict[str, Any]) -> None:
    """Start a new game in the same room (clears history)."""
    try:
        room_id = data.get('room_id', '')

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
        update_room_activity(room_id)

        emit('new_game_started', {'message': 'New game started. Set your numbers.'}, room=room_id)
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
    logger.info(f"Room timeout: {ROOM_INACTIVITY_TIMEOUT_SECONDS} seconds")
    logger.info("=" * 50)
    socketio.run(app, host=HOST, port=PORT, debug=DEBUG, allow_unsafe_werkzeug=DEBUG)
