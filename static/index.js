/**
 * 4-Digit Number Guessing Game - Index Page
 *
 * Handles room creation and joining with player names.
 */

/* global io */
(function () {
  'use strict';

  var socket = io();
  var createBtn = document.getElementById('createRoomBtn');
  var createResult = document.getElementById('createResult');
  var createNameInput = document.getElementById('createPlayerName');
  var joinBtn = document.getElementById('joinRoomBtn');
  var joinResult = document.getElementById('joinResult');
  var joinNameInput = document.getElementById('joinPlayerName');
  var roomCodeInput = document.getElementById('roomCode');

  /**
   * Store player name in sessionStorage for room page.
   * @param {string} name - Player name.
   */
  function storePlayerName(name) {
    sessionStorage.setItem('playerName', name || '');
  }

  createBtn.addEventListener('click', function () {
    var name = (createNameInput.value || '').trim();
    storePlayerName(name);
    socket.emit('create_room', {});
  });

  socket.on('room_created', function (data) {
    createResult.textContent = 'Room created: ' + data.room_id + '. Redirecting...';
    createResult.style.display = 'block';
    window.location.href = '/room/' + data.room_id + '?as=1';
  });

  joinBtn.addEventListener('click', function () {
    var code = (roomCodeInput.value || '').trim().toUpperCase();
    if (!code) {
      joinResult.textContent = 'Enter a room code.';
      joinResult.style.display = 'block';
      return;
    }
    var name = (joinNameInput.value || '').trim();
    storePlayerName(name);
    window.location.href = '/room/' + code + '?as=2';
  });

  // Handle Enter key for room code input
  roomCodeInput.addEventListener('keypress', function (e) {
    if (e.key === 'Enter') {
      joinBtn.click();
    }
  });
})();
