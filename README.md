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

### Docker

```bash
# Using Docker Compose (recommended)
docker-compose up -d

# Or build and run manually
docker build -t number-guess-game .
docker run -p 5000:5000 \
  -e SECRET_KEY=your-secret-key \
  -e ADMIN_KEY=your-admin-key \
  number-guess-game
```

### Using Make

```bash
# Show all available commands
make help

# Install and run
make install
make run

# Run tests
make test

# Docker commands
make docker        # Build and run
make docker-logs   # View logs
make docker-stop   # Stop container
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
├── app.py                  # Main Flask/SocketIO application
├── config.py               # Configuration constants
├── requirements.txt        # Base dependencies
├── requirements-prod.txt   # Production dependencies (Gunicorn)
├── requirements-dev.txt    # Development dependencies
├── Dockerfile              # Container image definition
├── docker-compose.yml      # Docker Compose configuration
├── docker-compose.prod.yml # Production overrides
├── Makefile                # Common commands
├── .github/
│   └── workflows/
│       └── ci.yml          # CI/CD pipeline
├── templates/              # Jinja2 HTML templates
│   ├── base.html           # Base template with theming
│   ├── index.html          # Home page
│   ├── room.html           # Game room
│   └── admin.html          # Admin panel
├── static/                 # Static assets
│   ├── client.js           # Game client logic
│   ├── index.js            # Home page logic
│   ├── room.js             # Room page bootstrap
│   └── style.css           # Styles
└── tests/                  # Test suite
    ├── conftest.py         # Pytest fixtures
    ├── test_game_logic.py
    ├── test_http_routes.py
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

## Production Deployment

### Using Docker Compose (Recommended)

```bash
# Create .env file with production settings
cat > .env << EOF
SECRET_KEY=your-secure-random-key-here
ADMIN_KEY=your-secure-admin-key-here
CORS_ORIGINS=https://yourdomain.com
LOG_LEVEL=WARNING
EOF

# Deploy with production settings
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# View logs
docker-compose logs -f
```

### Using Gunicorn Directly

```bash
# Install production dependencies
pip install -r requirements-prod.txt

# Run with Gunicorn
gunicorn --worker-class eventlet -w 1 -b 0.0.0.0:5000 app:app
```

### CI/CD Pipeline

The repository includes a GitHub Actions workflow that:

1. **Lint** - Checks code quality with flake8
2. **Test** - Runs pytest with coverage
3. **Build** - Builds and tests Docker image
4. **Deploy** - Ready for production deployment (manual trigger)

## Security Considerations

- **Change default keys**: Always set `SECRET_KEY` and `ADMIN_KEY` in production
- **CORS**: Configure `CORS_ORIGINS` to only allow your domain
- **HTTPS**: Use a reverse proxy (nginx) with SSL in production
- **Rate limiting**: Built-in rate limiting for admin endpoints
- **Non-root user**: Docker container runs as non-root user

## License

MIT License - see LICENSE file for details.
