# 4-Digit Number Guessing Game

A real-time multiplayer web game where two players try to guess each other's secret 4-digit numbers. Built with Flask and Socket.IO for instant WebSocket communication.

## How to Play

1. **Create or Join a Room**: One player creates a room and shares the 6-character room code
2. **Set Your Secret**: Each player picks a 4-digit number (1000-9999) that their opponent must guess
3. **Take Turns Guessing**: Players alternate guessing each other's numbers
4. **Win**: First player to correctly guess their opponent's number wins!

After each guess, you'll see how many digits you got in the correct position.

## Quick Start

### Prerequisites

- Python 3.8+
- pip

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd fantastic-octo-invention

# Install dependencies
pip install -r requirements.txt

# Run the server
python app.py
```

The server will start at `http://localhost:5000`

### Docker (Optional)

```bash
# Build and run with Docker
docker build -t number-guess-game .
docker run -p 5000:5000 number-guess-game
```

## Configuration

All configuration is done via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `false` | Enable debug mode (set to `true` for development) |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `5000` | Server port |
| `SECRET_KEY` | `dev-secret-key...` | Flask session secret (change in production!) |
| `DB_PATH` | `game.db` | SQLite database file path |
| `ADMIN_KEY` | `changeme` | Admin panel access key (change in production!) |
| `CORS_ORIGINS` | `localhost` | Comma-separated allowed origins for WebSocket |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `TURN_TIMEOUT_SECONDS` | `60` | Turn timeout in seconds (0 to disable) |

### Example Production Configuration

```bash
export DEBUG=false
export SECRET_KEY="your-secure-random-key-here"
export ADMIN_KEY="your-secure-admin-key-here"
export CORS_ORIGINS="https://yourdomain.com"
export LOG_LEVEL=INFO
```

## API Documentation

### HTTP Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Home page - create/join rooms |
| `/room/<room_id>` | GET | Game room page |
| `/health` | GET | Health check (returns JSON) |
| `/admin` | GET | Admin panel (requires auth) |
| `/admin/kill/<room_id>` | GET/POST | Delete a room |
| `/admin/reset/<room_id>` | GET/POST | Reset a room |

### Admin Authentication

Use the `X-Admin-Key` header:

```bash
curl -H "X-Admin-Key: your-admin-key" http://localhost:5000/admin
```

### Socket.IO Events

See [SOCKETIO_EVENTS.md](SOCKETIO_EVENTS.md) for detailed WebSocket API documentation.

## Project Structure

```
fantastic-octo-invention/
├── app.py              # Main Flask/SocketIO application
├── config.py           # Configuration constants
├── requirements.txt    # Production dependencies
├── requirements-dev.txt # Development dependencies
├── templates/          # Jinja2 HTML templates
│   ├── base.html       # Base template with theming
│   ├── index.html      # Home page
│   ├── room.html       # Game room
│   └── admin.html      # Admin panel
├── static/             # Static assets
│   ├── client.js       # Game client logic
│   ├── index.js        # Home page logic
│   ├── room.js         # Room page bootstrap
│   └── style.css       # Styles
└── tests/              # Test suite
    ├── test_game_logic.py
    └── test_socketio_events.py
```

## Development

### Setup Development Environment

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run with debug mode
DEBUG=true python app.py
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_game_logic.py -v
```

### Code Quality

```bash
# Lint code
flake8 .

# Type checking
mypy app.py config.py

# Format code
black .
```

## Security Considerations

- **Change default keys**: Always set `SECRET_KEY` and `ADMIN_KEY` in production
- **CORS**: Configure `CORS_ORIGINS` to only allow your domain
- **HTTPS**: Use a reverse proxy (nginx) with SSL in production
- **Rate limiting**: Built-in rate limiting for admin endpoints

## License

MIT License - see LICENSE file for details.
