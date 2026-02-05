# Repository Upgrade Plan

This document outlines a phased approach to improve the codebase from its current state (4.1/10) to production-ready quality.

---

## Phase 1: Critical Security & Stability (Priority: Immediate)

### 1.1 Fix CORS Configuration
**File:** `app.py:18`
```python
# Current (insecure)
cors_allowed_origins="*"

# Improved
cors_allowed_origins=os.environ.get('CORS_ORIGINS', 'http://localhost:5000').split(',')
```
**Why:** Prevents unauthorized sites from connecting to your Socket.IO server.

### 1.2 Secure Admin Authentication
**File:** `app.py:95-103`
- Remove `request.args.get('key')` - keys in URLs are logged/exposed
- Keep only header-based auth (`X-Admin-Key`)
- Add rate limiting (5 attempts per minute)
- Log failed authentication attempts

### 1.3 Add Error Handling
**Files:** `app.py`, `static/client.js`
- Wrap all database operations in `try/except`
- Add `try/catch` blocks in JavaScript
- Return user-friendly error messages
- Log errors with stack traces

### 1.4 Fix Race Conditions
**File:** `app.py`
```python
import threading
rooms_lock = threading.Lock()

# Use context manager for thread-safe access
with rooms_lock:
    rooms_runtime[room_id]['finished'][player] = True
```

### 1.5 Disable Debug Mode
**File:** `app.py`
```python
# Use environment variable
DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'
socketio.run(app, debug=DEBUG, ...)
```

---

## Phase 2: Code Quality & Maintainability (Priority: High)

### 2.1 Implement Proper Logging
**Replace all `print()` statements with logging module:**
```python
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Replace: print(f"Room {room_id} created")
# With:    logger.info(f"Room {room_id} created")
```

### 2.2 Extract Constants
**Create `config.py`:**
```python
# Game settings
DIGIT_COUNT = 4
MIN_SECRET = 1000
MAX_SECRET = 9999
ROOM_ID_LENGTH = 6
TURN_TIMEOUT_SECONDS = 60

# Server settings
ADMIN_KEY = os.environ.get('ADMIN_KEY', 'changeme')
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key')
DATABASE_PATH = os.environ.get('DATABASE_PATH', 'game.db')
```

### 2.3 Add Type Hints
```python
def count_matches(secret: str, guess: str) -> int:
    """Count matching digits between secret and guess."""
    ...

def create_room() -> tuple[str, str]:
    """Create a new room and return (room_id, token)."""
    ...
```

### 2.4 Add Docstrings
Document all functions with:
- Purpose description
- Parameter explanations
- Return value description
- Example usage (for complex functions)

### 2.5 Reduce Code Duplication
- Extract input validation into reusable functions
- Create database helper functions (connection management)
- Consolidate Socket.IO event response patterns

---

## Phase 3: Documentation (Priority: High)

### 3.1 Create README.md
```markdown
# Number Guessing Game

A 2-player web-based number guessing game with real-time WebSocket communication.

## Quick Start
pip install -r requirements.txt
python app.py

## Environment Variables
- ADMIN_KEY: Admin panel access key (default: changeme)
- SECRET_KEY: Flask session secret
- CORS_ORIGINS: Comma-separated allowed origins

## How to Play
1. Create or join a room
2. Set your 4-digit secret number (1000-9999)
3. Take turns guessing opponent's number
4. First to guess correctly wins!
```

### 3.2 Create API Documentation
Document all Socket.IO events:
- `create_room` - Create new game room
- `join_room` - Join existing room
- `submit_secret` - Submit secret number
- `submit_guess` - Submit guess
- `rejoin` - Reconnect to room

### 3.3 Add Code Comments
Add inline comments for complex logic (e.g., `count_matches` algorithm).

---

## Phase 4: Testing (Priority: High)

### 4.1 Set Up Testing Framework
```bash
pip install pytest pytest-cov pytest-asyncio
```

**Create `requirements-dev.txt`:**
```
pytest>=7.0.0
pytest-cov>=4.0.0
pytest-asyncio>=0.21.0
flake8>=6.0.0
black>=23.0.0
mypy>=1.0.0
```

### 4.2 Unit Tests
**Create `tests/test_game_logic.py`:**
```python
def test_count_matches_exact():
    assert count_matches("1234", "1234") == 4

def test_count_matches_partial():
    assert count_matches("1234", "1243") == 2

def test_count_matches_none():
    assert count_matches("1234", "5678") == 0
```

### 4.3 Integration Tests
- Test room creation and joining flow
- Test game progression (secrets, guesses, win condition)
- Test admin endpoints

### 4.4 Add Test Coverage Target
Aim for 80%+ code coverage.

---

## Phase 5: Infrastructure (Priority: Medium)

### 5.1 Database Improvements
- Add connection pooling
- Create database migrations with Alembic
- Add indexes for frequently queried columns

### 5.2 Rate Limiting
```python
from flask_limiter import Limiter
limiter = Limiter(app, key_func=get_remote_address)

@app.route('/admin')
@limiter.limit("5 per minute")
@admin_required
def admin():
    ...
```

### 5.3 Server-Side Timeout
Implement server-side turn timeout:
```python
import threading

def timeout_turn(room_id, player):
    # Auto-skip turn after timeout
    ...

timer = threading.Timer(60.0, timeout_turn, args=[room_id, player])
timer.start()
```

### 5.4 Health Check Endpoint
```python
@app.route('/health')
def health():
    return {'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()}
```

---

## Phase 6: DevOps & Deployment (Priority: Medium)

### 6.1 Docker Support
**Create `Dockerfile`:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "app.py"]
```

**Create `docker-compose.yml`:**
```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "5000:5000"
    environment:
      - ADMIN_KEY=${ADMIN_KEY}
      - SECRET_KEY=${SECRET_KEY}
```

### 6.2 CI/CD Pipeline
**Create `.github/workflows/ci.yml`:**
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: flake8 .
      - run: pytest --cov=. --cov-report=xml
```

### 6.3 Production Server
Replace Flask dev server with Gunicorn:
```bash
pip install gunicorn
gunicorn --worker-class eventlet -w 1 app:app
```

---

## Phase 7: Feature Enhancements (Priority: Low)

### 7.1 User Experience
- Add sound effects for events
- Show opponent's typing indicator
- Add room chat functionality
- Implement game replay/history

### 7.2 Game Modes
- Configurable digit count (4-6 digits)
- Timed mode with shorter turns
- Best of 3/5 series

### 7.3 Persistence
- User accounts and authentication
- Leaderboard and statistics
- Game history

---

## Implementation Timeline

| Phase | Tasks | Estimated Effort |
|-------|-------|------------------|
| 1 | Security & Stability | Small |
| 2 | Code Quality | Medium |
| 3 | Documentation | Small |
| 4 | Testing | Medium |
| 5 | Infrastructure | Medium |
| 6 | DevOps | Medium |
| 7 | Features | Large |

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Test Coverage | 0% | 80%+ |
| Documentation | None | Complete |
| Security Score | 5/10 | 9/10 |
| Code Quality | 6/10 | 8/10 |
| Overall Score | 4.1/10 | 8/10+ |
