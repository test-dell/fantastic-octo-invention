/**
 * 4-Digit Number Guessing Game - Client
 *
 * Handles Socket.IO communication and UI updates for the game room.
 */

/* global io */
(function () {
  'use strict';

  // Configuration constants
  var CONFIG = {
    DIGIT_COUNT: 4,
    MIN_SECRET: 1000,
    MAX_SECRET: 9999,
    STORAGE_PREFIX: 'ng_token_'
  };

  /**
   * Validate a 4-digit number string.
   * @param {string} n - The number to validate.
   * @returns {boolean} True if valid.
   */
  function isValidFourDigit(n) {
    if (!n || typeof n !== 'string') return false;
    var pattern = new RegExp('^\\d{' + CONFIG.DIGIT_COUNT + '}$');
    if (!pattern.test(n)) return false;
    var num = parseInt(n, 10);
    return num >= CONFIG.MIN_SECRET && num <= CONFIG.MAX_SECRET;
  }

  /**
   * Format milliseconds timestamp as MM:SS timer display.
   * @param {number|null} ms - Start timestamp in milliseconds.
   * @returns {string} Formatted time string.
   */
  function formatTimer(ms) {
    if (!ms) return '00:00';
    var delta = Math.max(0, Date.now() - ms);
    var s = Math.floor(delta / 1000);
    var m = Math.floor(s / 60);
    var sec = s % 60;
    return String(m).padStart(2, '0') + ':' + String(sec).padStart(2, '0');
  }

  /**
   * Escape HTML to prevent XSS when inserting user content.
   * @param {string} str - String to escape.
   * @returns {string} Escaped string.
   */
  function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  /**
   * Safely set text content of an element.
   * @param {HTMLElement|null} el - Target element.
   * @param {string} text - Text to set.
   */
  function safeSetText(el, text) {
    if (el) {
      el.textContent = text;
    }
  }

  /**
   * Setup the game room page.
   * @param {string} roomId - The room identifier.
   * @param {number} desiredPlayer - Requested player number (1 or 2).
   * @param {string|null} token - Reconnection token if available.
   */
  function setupRoomPage(roomId, desiredPlayer, token) {
    try {
      var socket = io();
      var myPlayer = null;
      var mySecret = { 1: null, 2: null };
      var timerInterval = null;

      // Cache DOM elements
      var el = {
        status: document.getElementById('statusBanner'),
        startBtn: document.getElementById('startBtn'),
        exitBtn: document.getElementById('exitBtn'),
        newGameBtn: document.getElementById('newGameBtn'),
        timerText: document.getElementById('timerText'),
        p1SecretInput: document.getElementById('p1Secret'),
        p1Set: document.getElementById('p1Set'),
        p1ShowHide: document.getElementById('p1ShowHide'),
        p1ResetSecret: document.getElementById('p1ResetSecret'),
        p1SecretDisplay: document.getElementById('p1SecretDisplay'),
        p1Guess: document.getElementById('p1Guess'),
        p1Submit: document.getElementById('p1Submit'),
        p1History: document.getElementById('p1History'),
        p1Card: document.getElementById('p1Card'),
        p1GuessCard: document.getElementById('p1GuessCard'),
        p2SecretInput: document.getElementById('p2Secret'),
        p2Set: document.getElementById('p2Set'),
        p2ShowHide: document.getElementById('p2ShowHide'),
        p2ResetSecret: document.getElementById('p2ResetSecret'),
        p2SecretDisplay: document.getElementById('p2SecretDisplay'),
        p2Guess: document.getElementById('p2Guess'),
        p2Submit: document.getElementById('p2Submit'),
        p2History: document.getElementById('p2History'),
        p2Card: document.getElementById('p2Card'),
        p2GuessCard: document.getElementById('p2GuessCard')
      };

      /**
       * Start the local timer display.
       * @param {number} ms - Start timestamp.
       */
      function startLocalTimer(ms) {
        try {
          if (timerInterval) clearInterval(timerInterval);
          safeSetText(el.timerText, formatTimer(ms));
          timerInterval = setInterval(function () {
            safeSetText(el.timerText, formatTimer(ms));
          }, 1000);
        } catch (e) {
          console.error('Error starting timer:', e);
        }
      }

      /**
       * Stop the local timer display.
       */
      function stopLocalTimer() {
        try {
          if (timerInterval) {
            clearInterval(timerInterval);
            timerInterval = null;
          }
          safeSetText(el.timerText, '00:00');
        } catch (e) {
          console.error('Error stopping timer:', e);
        }
      }

      /**
       * Update UI input states based on game state.
       * @param {boolean} enable - Whether inputs should be enabled.
       * @param {number} currentTurn - Current player's turn.
       * @param {Object} finished - Which players have finished.
       */
      function enforceInputState(enable, currentTurn, finished) {
        try {
          finished = finished || { 1: false, 2: false };
          var p1Active = !!(enable && currentTurn === 1 && !finished[1]);
          var p2Active = !!(enable && currentTurn === 2 && !finished[2]);

          if (el.p1Guess) el.p1Guess.disabled = !p1Active;
          if (el.p1Submit) el.p1Submit.disabled = !p1Active;
          if (el.p2Guess) el.p2Guess.disabled = !p2Active;
          if (el.p2Submit) el.p2Submit.disabled = !p2Active;
        } catch (e) {
          console.error('Error updating input state:', e);
        }
      }

      /**
       * Render guess history to a table body.
       * @param {HTMLElement} tbody - Target table body element.
       * @param {Array} items - History items to render.
       */
      function renderHistory(tbody, items) {
        try {
          if (!tbody) return;
          // Clear existing content safely
          while (tbody.firstChild) {
            tbody.removeChild(tbody.firstChild);
          }
          items.forEach(function (it, idx) {
            addHistoryRow(tbody, it.guess, it.outcome, idx + 1);
          });
        } catch (e) {
          console.error('Error rendering history:', e);
        }
      }

      /**
       * Add a single row to the history table.
       * @param {HTMLElement} tbody - Target table body.
       * @param {string} guess - The guess made.
       * @param {string} outcome - The result.
       * @param {number} idx - Row number.
       */
      function addHistoryRow(tbody, guess, outcome, idx) {
        try {
          if (!tbody) return;
          var tr = document.createElement('tr');
          var n = idx || (tbody.children.length + 1);

          // Create cells safely using textContent (prevents XSS)
          var tdNum = document.createElement('td');
          tdNum.textContent = String(n);

          var tdGuess = document.createElement('td');
          tdGuess.textContent = String(guess);

          var tdOutcome = document.createElement('td');
          tdOutcome.textContent = String(outcome);

          tr.appendChild(tdNum);
          tr.appendChild(tdGuess);
          tr.appendChild(tdOutcome);
          tbody.appendChild(tr);
        } catch (e) {
          console.error('Error adding history row:', e);
        }
      }

      /**
       * Hide UI elements not relevant to the player's role.
       * @param {number} player - The player number.
       */
      function gateUIForRole(player) {
        try {
          if (player === 1 && el.p2Card) {
            el.p2Card.classList.add('hidden');
          }
          if (player === 2 && el.p1Card) {
            el.p1Card.classList.add('hidden');
          }
        } catch (e) {
          console.error('Error gating UI:', e);
        }
      }

      /**
       * Handle setting a secret for a player.
       * @param {number} playerNum - Player number (1 or 2).
       * @param {HTMLInputElement} input - Secret input element.
       * @param {HTMLElement} display - Secret display element.
       * @param {HTMLButtonElement} setBtn - Set button element.
       * @param {HTMLButtonElement} resetBtn - Reset button element.
       */
      function handleSetSecret(playerNum, input, display, setBtn, resetBtn) {
        try {
          var val = (input.value || '').trim();
          if (!isValidFourDigit(val)) {
            alert('Enter a valid 4-digit number (' + CONFIG.MIN_SECRET + '–' + CONFIG.MAX_SECRET + ').');
            return;
          }
          mySecret[playerNum] = val;
          safeSetText(display, '•••• (hidden)');
          input.disabled = true;
          setBtn.disabled = true;
          resetBtn.disabled = false;
          socket.emit('set_secret', { room_id: roomId, player: playerNum, secret: val });
        } catch (e) {
          console.error('Error setting secret:', e);
          alert('Failed to set secret. Please try again.');
        }
      }

      /**
       * Handle resetting a secret for a player.
       * @param {number} playerNum - Player number (1 or 2).
       * @param {HTMLInputElement} input - Secret input element.
       * @param {HTMLElement} display - Secret display element.
       * @param {HTMLButtonElement} setBtn - Set button element.
       * @param {HTMLButtonElement} resetBtn - Reset button element.
       */
      function handleResetSecret(playerNum, input, display, setBtn, resetBtn) {
        try {
          socket.emit('reset_secret', { room_id: roomId, player: playerNum });
          mySecret[playerNum] = null;
          safeSetText(display, '—');
          input.disabled = false;
          setBtn.disabled = false;
          resetBtn.disabled = true;
          input.value = '';
        } catch (e) {
          console.error('Error resetting secret:', e);
        }
      }

      /**
       * Handle toggling secret visibility.
       * @param {number} playerNum - Player number.
       * @param {HTMLElement} display - Display element.
       */
      function handleShowHide(playerNum, display) {
        try {
          if (mySecret[playerNum] === null) return;
          var isVisible = display.dataset.visible === 'true';
          if (!isVisible) {
            safeSetText(display, mySecret[playerNum]);
            display.dataset.visible = 'true';
          } else {
            safeSetText(display, '•••• (hidden)');
            display.dataset.visible = 'false';
          }
        } catch (e) {
          console.error('Error toggling secret visibility:', e);
        }
      }

      /**
       * Handle submitting a guess.
       * @param {number} playerNum - Player number.
       * @param {HTMLInputElement} guessInput - Guess input element.
       */
      function handleSubmitGuess(playerNum, guessInput) {
        try {
          var val = (guessInput.value || '').trim();
          if (!isValidFourDigit(val)) {
            alert('Enter a valid 4-digit number (' + CONFIG.MIN_SECRET + '–' + CONFIG.MAX_SECRET + ').');
            return;
          }
          socket.emit('submit_guess', { room_id: roomId, player: playerNum, guess: val });
          guessInput.value = '';
        } catch (e) {
          console.error('Error submitting guess:', e);
          alert('Failed to submit guess. Please try again.');
        }
      }

      // Socket event handlers
      socket.on('connect', function () {
        try {
          socket.emit('join_room', { room_id: roomId, player: desiredPlayer, token: token });
        } catch (e) {
          console.error('Error on connect:', e);
        }
      });

      socket.on('joined', function (data) {
        try {
          myPlayer = data.player;
          if (data.token) {
            localStorage.setItem(CONFIG.STORAGE_PREFIX + data.room_id, data.token);
          }
          safeSetText(el.status, 'Joined as Player ' + data.player + '. Set your number.');
          gateUIForRole(data.player);
          enforceInputState(false);
        } catch (e) {
          console.error('Error handling joined:', e);
        }
      });

      socket.on('error', function (data) {
        try {
          var message = (data && data.message) || 'An error occurred';
          alert(message);
        } catch (e) {
          console.error('Error handling error event:', e);
        }
      });

      socket.on('system', function (data) {
        try {
          safeSetText(el.status, data.message);
        } catch (e) {
          console.error('Error handling system message:', e);
        }
      });

      socket.on('state', function (state) {
        try {
          var ready = state.readiness && state.readiness.p1_set && state.readiness.p2_set;
          if (el.startBtn) el.startBtn.disabled = !ready || state.started;

          if (state.started) {
            safeSetText(el.status, 'Game started. Player ' + state.current_turn + "'s turn.");
            enforceInputState(true, state.current_turn, state.finished);
            if (state.timer_start_ms) startLocalTimer(state.timer_start_ms);
          } else {
            var statusMsg = ready ? 'Both numbers set. Click Start Game.' : 'Waiting for both players to set numbers.';
            safeSetText(el.status, statusMsg);
            enforceInputState(false);
          }

          if (state.history) {
            renderHistory(el.p1History, state.history[1] || []);
            renderHistory(el.p2History, state.history[2] || []);
          }
        } catch (e) {
          console.error('Error handling state:', e);
        }
      });

      socket.on('secret_ack', function () {
        // Secret acknowledged - no action needed
      });

      socket.on('game_started', function (data) {
        try {
          safeSetText(el.status, 'Game started. Player ' + data.current_turn + "'s turn.");
          if (data.timer_start_ms) startLocalTimer(data.timer_start_ms);
        } catch (e) {
          console.error('Error handling game_started:', e);
        }
      });

      socket.on('turn', function (data) {
        try {
          safeSetText(el.status, 'Player ' + data.current_turn + "'s turn.");
          enforceInputState(true, data.current_turn);
        } catch (e) {
          console.error('Error handling turn:', e);
        }
      });

      socket.on('guess_result', function (data) {
        try {
          if (data.player === 1) addHistoryRow(el.p1History, data.guess, data.outcome);
          if (data.player === 2) addHistoryRow(el.p2History, data.guess, data.outcome);
        } catch (e) {
          console.error('Error handling guess_result:', e);
        }
      });

      socket.on('game_over', function (data) {
        try {
          safeSetText(el.status, 'Player ' + data.winner + ' wins! ' + data.message);
          enforceInputState(false);
          stopLocalTimer();
          if (el.newGameBtn) el.newGameBtn.disabled = false;
        } catch (e) {
          console.error('Error handling game_over:', e);
        }
      });

      socket.on('disconnect', function () {
        try {
          safeSetText(el.status, 'Disconnected from server. Refresh to reconnect.');
        } catch (e) {
          console.error('Error handling disconnect:', e);
        }
      });

      // Event listeners for Player 1
      if (el.p1Set) {
        el.p1Set.addEventListener('click', function () {
          handleSetSecret(1, el.p1SecretInput, el.p1SecretDisplay, el.p1Set, el.p1ResetSecret);
        });
      }

      if (el.p1ResetSecret) {
        el.p1ResetSecret.addEventListener('click', function () {
          handleResetSecret(1, el.p1SecretInput, el.p1SecretDisplay, el.p1Set, el.p1ResetSecret);
        });
      }

      if (el.p1ShowHide) {
        el.p1ShowHide.addEventListener('click', function () {
          handleShowHide(1, el.p1SecretDisplay);
        });
      }

      if (el.p1Submit) {
        el.p1Submit.addEventListener('click', function () {
          handleSubmitGuess(1, el.p1Guess);
        });
      }

      // Event listeners for Player 2
      if (el.p2Set) {
        el.p2Set.addEventListener('click', function () {
          handleSetSecret(2, el.p2SecretInput, el.p2SecretDisplay, el.p2Set, el.p2ResetSecret);
        });
      }

      if (el.p2ResetSecret) {
        el.p2ResetSecret.addEventListener('click', function () {
          handleResetSecret(2, el.p2SecretInput, el.p2SecretDisplay, el.p2Set, el.p2ResetSecret);
        });
      }

      if (el.p2ShowHide) {
        el.p2ShowHide.addEventListener('click', function () {
          handleShowHide(2, el.p2SecretDisplay);
        });
      }

      if (el.p2Submit) {
        el.p2Submit.addEventListener('click', function () {
          handleSubmitGuess(2, el.p2Guess);
        });
      }

      // Shared controls
      if (el.startBtn) {
        el.startBtn.addEventListener('click', function () {
          try {
            socket.emit('start_game', { room_id: roomId });
          } catch (e) {
            console.error('Error starting game:', e);
          }
        });
      }

      if (el.exitBtn) {
        el.exitBtn.addEventListener('click', function () {
          try {
            if (myPlayer) {
              socket.emit('leave_room', { room_id: roomId, player: myPlayer });
            }
            window.location.href = '/';
          } catch (e) {
            console.error('Error exiting:', e);
            window.location.href = '/';
          }
        });
      }

      if (el.newGameBtn) {
        el.newGameBtn.addEventListener('click', function () {
          try {
            socket.emit('new_game', { room_id: roomId });
            stopLocalTimer();
            el.newGameBtn.disabled = true;
          } catch (e) {
            console.error('Error starting new game:', e);
          }
        });
      }

    } catch (e) {
      console.error('Fatal error setting up room page:', e);
      alert('Failed to initialize game. Please refresh the page.');
    }
  }

  // Export to window
  window.setupRoomPage = setupRoomPage;
})();
