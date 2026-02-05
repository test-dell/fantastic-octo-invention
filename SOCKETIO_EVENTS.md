# Socket.IO Events API

This document describes all Socket.IO events used for real-time communication in the Number Guessing Game.

## Connection

Connect to the Socket.IO server at the root URL:

```javascript
const socket = io('http://localhost:5000');
```

## Client -> Server Events

### `create_room`

Create a new game room.

**Request:**
```javascript
socket.emit('create_room', {});
```

**Response Event:** `room_created`

---

### `join_room`

Join an existing game room.

**Request:**
```javascript
socket.emit('join_room', {
  room_id: 'ABC123',    // Required: 6-character room code
  player: 1,            // Required: Player number (1 or 2)
  token: 'abc...'       // Optional: Reconnection token
});
```

**Response Events:** `joined` or `error`

---

### `leave_room`

Leave the current game room.

**Request:**
```javascript
socket.emit('leave_room', {
  room_id: 'ABC123',
  player: 1
});
```

**Response Event:** `system` (broadcast to room)

---

### `set_secret`

Set your secret number before the game starts.

**Request:**
```javascript
socket.emit('set_secret', {
  room_id: 'ABC123',
  player: 1,
  secret: '1234'        // 4-digit number (1000-9999)
});
```

**Response Events:** `secret_ack`, `system`, `state` or `error`

---

### `reset_secret`

Reset your secret number (only before game starts).

**Request:**
```javascript
socket.emit('reset_secret', {
  room_id: 'ABC123',
  player: 1
});
```

**Response Events:** `system`, `state` or `error`

---

### `start_game`

Start the game (requires both players to have set secrets).

**Request:**
```javascript
socket.emit('start_game', {
  room_id: 'ABC123'
});
```

**Response Events:** `game_started`, `state` or `error`

---

### `submit_guess`

Submit a guess for your opponent's number.

**Request:**
```javascript
socket.emit('submit_guess', {
  room_id: 'ABC123',
  player: 1,
  guess: '5678'         // 4-digit number (1000-9999)
});
```

**Response Events:** `guess_result`, `turn`/`game_over`, `state` or `error`

---

### `new_game`

Start a new game in the same room.

**Request:**
```javascript
socket.emit('new_game', {
  room_id: 'ABC123'
});
```

**Response Events:** `system`, `state`

---

## Server -> Client Events

### `room_created`

Sent when a new room is successfully created.

**Payload:**
```javascript
{
  room_id: 'ABC123'     // The new room code
}
```

---

### `joined`

Sent when successfully joined a room.

**Payload:**
```javascript
{
  room_id: 'ABC123',
  player: 1,            // Your player number
  token: 'abc123...'    // Save this for reconnection
}
```

---

### `error`

Sent when an operation fails.

**Payload:**
```javascript
{
  message: 'Error description'
}
```

**Common Errors:**
- `'Room not found.'`
- `'Player X slot already taken.'`
- `'Invalid player number.'`
- `'Secret must be a 4-digit number between 1000 and 9999.'`
- `'Cannot set secret after game has started.'`
- `'Both players must set their numbers.'`
- `'Game has not started.'`
- `'Not your turn.'`
- `'Unauthorized player.'`

---

### `system`

System messages broadcast to all players in a room.

**Payload:**
```javascript
{
  message: 'Player 1 joined.'
}
```

---

### `state`

Full game state update. Sent frequently to keep clients synchronized.

**Payload:**
```javascript
{
  started: true,              // Game in progress?
  current_turn: 1,            // Whose turn (1 or 2)
  finished: {                 // Which players have won
    1: false,
    2: false
  },
  history: {                  // Guess history per player
    1: [
      { guess: '1234', outcome: '2 correct' },
      { guess: '1256', outcome: '3 correct' }
    ],
    2: [
      { guess: '5678', outcome: '0 correct' }
    ]
  },
  readiness: {                // Which players set secrets
    p1_set: true,
    p2_set: true
  },
  timer_start_ms: 1699999999000  // Turn start timestamp
}
```

---

### `secret_ack`

Acknowledgment that secret was set successfully.

**Payload:**
```javascript
{
  player: 1
}
```

---

### `game_started`

Sent to all players when the game begins.

**Payload:**
```javascript
{
  current_turn: 1,
  timer_start_ms: 1699999999000
}
```

---

### `guess_result`

Result of a guess attempt.

**Payload:**
```javascript
{
  player: 1,
  guess: '1234',
  outcome: '2 correct'  // or 'Correct! You win!'
}
```

---

### `turn`

Indicates turn change.

**Payload:**
```javascript
{
  current_turn: 2
}
```

---

### `game_over`

Game has ended.

**Payload:**
```javascript
{
  winner: 1,
  message: 'Player 1 wins!'
}
```

---

## Example Client Implementation

```javascript
const socket = io();

// Connect and join room
socket.on('connect', () => {
  socket.emit('join_room', {
    room_id: 'ABC123',
    player: 1
  });
});

// Handle successful join
socket.on('joined', (data) => {
  console.log(`Joined as Player ${data.player}`);
  localStorage.setItem('token', data.token);  // Save for reconnection
});

// Handle errors
socket.on('error', (data) => {
  alert(data.message);
});

// Handle state updates
socket.on('state', (state) => {
  updateUI(state);
});

// Handle game over
socket.on('game_over', (data) => {
  alert(`Player ${data.winner} wins!`);
});
```

## Reconnection

To reconnect after a disconnect, use the saved token:

```javascript
socket.emit('join_room', {
  room_id: 'ABC123',
  player: 0,  // Will be ignored when token is valid
  token: localStorage.getItem('token')
});
```

The server will automatically restore your player position.
