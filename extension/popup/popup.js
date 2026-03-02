// popup.js — MeetIQ Extension Popup

// ─── State ─────────────────────────────────────────────────────────────────────
let isRecording = false;
let timerInterval = null;
let startTime = null;
let selectedPurpose = '';

// ─── DOM refs ──────────────────────────────────────────────────────────────────
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const timerEl = document.getElementById('timer');
const errorBanner = document.getElementById('error-banner');
const resultBanner = document.getElementById('result-banner');
const btnRecord = document.getElementById('btn-record');
const btnIcon = document.getElementById('btn-icon');
const btnLabel = document.getElementById('btn-label');
const btnResetState = document.getElementById('btn-reset-state');
const btnTestConnection = document.getElementById('btn-test-connection');
const btnDashboard = document.getElementById('btn-dashboard');
const btnSettings = document.getElementById('btn-settings');
const btnSaveSettings = document.getElementById('btn-save-settings');

// ─── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  await loadSettings();
  await syncState();
  await loadMeetings();
  await prefillFromActiveTab();
  setupNav();
  setupPurposeChips();
  setupRecordButton();
  setupSettingsForm();
  await applyMeetingTypeHint();

  // Listen for messages from background
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === 'ANALYSIS_DONE') {
      showResultBanner(msg.meetingId);
      loadMeetings();
    }
  });

  // Troubleshooting buttons
  btnResetState?.addEventListener('click', async () => {
    if (!confirm('Are you sure? This will clear any active recording state from the extension.')) return;
    await chrome.runtime.sendMessage({ type: 'RESET_STATE' });
    window.location.reload();
  });

  btnTestConnection?.addEventListener('click', async () => {
    const originalText = btnTestConnection.innerText;
    btnTestConnection.innerText = 'Testing...';
    try {
      const { settings = {} } = await chrome.storage.local.get('settings');
      const base = settings.apiUrl || 'http://localhost:8000';
      const res = await fetch(`${base}/health`);
      if (res.ok) {
        alert('Connected successfully! Backend is reachable.');
      } else {
        alert('Backend reached, but it returned an error status: ' + res.status);
      }
    } catch (err) {
      alert('Failed to reach backend! Error: ' + err.message);
    } finally {
      btnTestConnection.innerText = originalText;
    }
  });

  if (resultBanner) {
    resultBanner.addEventListener('click', () => {
      const id = resultBanner.dataset.meetingId;
      if (id) chrome.tabs.create({ url: chrome.runtime.getURL(`dashboard/index.html#meeting-id=${id}`) });
    });
  }
});

// ─── Core Logic ───────────────────────────────────────────────────────────────

async function syncState() {
  try {
    const state = await chrome.runtime.sendMessage({ type: 'GET_STATE' });
    if (state?.activeMeeting) {
      const m = state.activeMeeting;
      if (m.status === 'processing') setProcessingUI();
      else if (m.status === 'error') setErrorUI();
      else if (m.status === 'recording') {
        isRecording = true;
        setRecordingUI(true, m.startedAt);
      } else setIdleUI();

      if (m.name) document.getElementById('meeting-name').value = m.name;
      if (m.participants?.length) document.getElementById('attendees').value = m.participants.join(', ');
      if (m.agenda) document.getElementById('agenda').value = m.agenda;
      if (m.meetingType) selectPurpose(m.meetingType, false);
    } else {
      setIdleUI();
    }
  } catch (e) { setIdleUI(); }
}

function setupRecordButton() {
  btnRecord?.addEventListener('click', async () => {
    if (isRecording) {
      setButtonLoading(true);
      const res = await chrome.runtime.sendMessage({ type: 'STOP_RECORDING' });
      setButtonLoading(false);
      if (res.ok) setProcessingUI();
      else showError(res.error || 'Failed to stop.');
    } else {
      try {
        setButtonLoading(true);
        // Request mic permission directly in popup to grant it to the extension
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        stream.getTracks().forEach(t => t.stop());

        const payload = {
          name: document.getElementById('meeting-name').value || 'New Meeting',
          agenda: document.getElementById('agenda').value,
          participants: document.getElementById('attendees').value.split(',').map(s => s.trim()).filter(Boolean),
          meetingType: selectedPurpose
        };

        const res = await chrome.runtime.sendMessage({
          type: 'START_RECORDING',
          payload: {
            ...payload,
            meetingType: selectedPurpose || 'discovery'
          }
        });
        setButtonLoading(false);

        if (res.ok) {
          isRecording = true;
          setRecordingUI(true, Date.now());
        } else {
          showError(res.error || 'Check extension requirements.');
          setIdleUI();
        }
      } catch (err) {
        setButtonLoading(false);
        showError('Microphone permission denied. Enable it in Chrome settings (site permissions).');
      }
    }
  });
}

// ─── UI State Managers ────────────────────────────────────────────────────────

function setRecordingUI(active, since = Date.now()) {
  isRecording = true;
  startTime = since;
  statusDot.className = 'status-dot recording';
  statusText.textContent = 'Recording active';
  timerEl.style.display = '';
  startTimer(since);
  btnRecord.className = 'btn-record stop';
  btnIcon.textContent = '⏹';
  btnLabel.textContent = 'Stop Recording';
  btnRecord.disabled = false;
  ['meeting-name', 'attendees', 'agenda'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.disabled = true;
  });
  document.querySelectorAll('.chip').forEach(c => c.style.pointerEvents = 'none');
}

function setIdleUI() {
  isRecording = false;
  stopTimer();
  statusDot.className = 'status-dot ready';
  statusText.textContent = 'Ready to record';
  timerEl.style.display = 'none';
  btnRecord.className = 'btn-record start';
  btnRecord.disabled = false;
  btnIcon.textContent = '⏺';
  btnLabel.textContent = 'Start Recording';
  ['meeting-name', 'attendees', 'agenda'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.disabled = false;
  });
  document.querySelectorAll('.chip').forEach(c => c.style.pointerEvents = '');
}

function setProcessingUI() {
  isRecording = false;
  stopTimer();
  statusDot.className = 'status-dot processing';
  statusText.textContent = 'Analyzing...';
  timerEl.style.display = 'none';
  btnRecord.className = 'btn-record start';
  btnRecord.disabled = true;
  btnIcon.textContent = '⏳';
  btnLabel.textContent = 'Processing';
}

function setErrorUI() {
  isRecording = false;
  stopTimer();
  statusDot.className = 'status-dot error';
  statusText.textContent = 'Error';
  timerEl.style.display = 'none';
  btnRecord.className = 'btn-record start';
  btnRecord.disabled = false;
  btnIcon.textContent = '⏺';
  btnLabel.textContent = 'Retry';
  showError('Analysis failed. Try resetting in Settings.');
}

function setButtonLoading(loading) {
  if (!btnRecord) return;
  btnRecord.disabled = loading;
  if (loading) btnLabel.textContent = '...';
}

function showResultBanner(id) {
  if (!resultBanner) return;
  resultBanner.dataset.meetingId = id;
  resultBanner.style.display = '';
  setIdleUI();
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function startTimer(since) {
  stopTimer();
  timerInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - since) / 1000);
    const m = String(Math.floor(elapsed / 60)).padStart(2, '0');
    const s = String(elapsed % 60).padStart(2, '0');
    timerEl.textContent = `${m}:${s}`;
  }, 1000);
}
function stopTimer() { clearInterval(timerInterval); timerInterval = null; }

function showError(msg) {
  if (!errorBanner) return;
  errorBanner.textContent = msg;
  errorBanner.style.display = '';
  setTimeout(() => { if (errorBanner) errorBanner.style.display = 'none'; }, 6000);
}

async function loadMeetings() {
  const { meetings = [] } = await chrome.storage.local.get('meetings');
  const list = document.getElementById('meetings-list');
  if (!list) return;

  if (meetings.length === 0) {
    list.innerHTML = '<div class="empty-state"><div class="empty-icon">🎙️</div><div>No recordings yet.</div></div>';
    return;
  }

  list.innerHTML = meetings.slice(0, 20).map(m => {
    const r = m.result || {};
    const color = { done: '#22c55e', recording: '#ef4444', processing: '#eab308', error: '#f87171' }[m.status] || '#64748b';
    const date = m.savedAt ? new Date(m.savedAt).toLocaleDateString() : '—';
    return `
      <div class="meeting-item" data-id="${m.meetingId}">
        <div class="meeting-status-dot" style="background:${color}"></div>
        <div class="meeting-info">
          <div class="meeting-name">${escHtml(r.meetingName || m.meetingId)}</div>
          <div class="meeting-meta">${date}</div>
        </div>
        <span class="meeting-badge ${m.status}">${m.status.toUpperCase()}</span>
      </div>
    `;
  }).join('');

  list.querySelectorAll('.meeting-item').forEach(item => {
    item.addEventListener('click', () => {
      chrome.tabs.create({ url: chrome.runtime.getURL(`dashboard/index.html#meeting-id=${item.dataset.id}`) });
    });
  });
}

async function loadSettings() {
  const { settings = {} } = await chrome.storage.local.get('settings');
  document.getElementById('setting-speaker').value = settings.speakerName || '';
  document.getElementById('setting-api').value = settings.apiUrl || 'http://localhost:8000';
  document.getElementById('setting-discord').value = settings.discordWebhook || '';
  document.getElementById('setting-slack').value = settings.slackWebhook || '';
}

function setupSettingsForm() {
  btnSaveSettings?.addEventListener('click', async () => {
    const settings = {
      speakerName: document.getElementById('setting-speaker').value.trim(),
      apiUrl: document.getElementById('setting-api').value.trim(),
      discordWebhook: document.getElementById('setting-discord').value.trim(),
      slackWebhook: document.getElementById('setting-slack').value.trim(),
    };
    await chrome.storage.local.set({ settings });
    btnSaveSettings.textContent = '✓ Saved';
    setTimeout(() => btnSaveSettings.textContent = 'Save Settings', 2000);
  });
}

function setupNav() {
  document.querySelectorAll('.nav-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const page = tab.dataset.page;
      document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById(`page-${page}`).classList.add('active');
      if (page === 'meetings') loadMeetings();
    });
  });

  btnDashboard?.addEventListener('click', () => {
    chrome.tabs.create({ url: chrome.runtime.getURL('dashboard/index.html') });
  });

  btnSettings?.addEventListener('click', () => {
    document.getElementById('nav-settings').click();
  });
}

function setupPurposeChips() {
  document.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const val = chip.dataset.val;
      selectPurpose(val === selectedPurpose ? '' : val, true);
    });
  });
}

function selectPurpose(val, userChosen = true) {
  selectedPurpose = val;
  document.querySelectorAll('.chip').forEach(c => {
    c.classList.toggle('active', c.dataset.val === val);
  });
}

async function prefillFromActiveTab() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || isRecording) return;
    const nameEl = document.getElementById('meeting-name');
    if (tab.url.includes('meet.google.com') && !nameEl.value) {
      nameEl.value = 'Google Meet';
    }
  } catch (e) { }
}

async function applyMeetingTypeHint() {
  try {
    const data = await chrome.storage.session.get('meetingTypeHint');
    const hint = data?.meetingTypeHint;
    if (hint && (Date.now() - hint.ts < 600000)) { // 10 min window
      const badge = document.getElementById('auto-detect-badge');
      if (badge && !selectedPurpose) {
        badge.textContent = `✨ Detected: ${hint.suggestedType}`;
        badge.style.display = 'inline-block';
        badge.onclick = () => {
          selectPurpose(hint.suggestedType);
          badge.style.display = 'none';
        };
      }
    }
  } catch (e) {
    // Session storage fallback
    const data = await chrome.storage.local.get('meetingTypeHint');
    const hint = data?.meetingTypeHint;
    if (hint && (Date.now() - hint.ts < 600000)) {
      const badge = document.getElementById('auto-detect-badge');
      if (badge && !selectedPurpose) {
        badge.textContent = `✨ Detected: ${hint.suggestedType}`;
        badge.style.display = 'inline-block';
        badge.onclick = () => {
          selectPurpose(hint.suggestedType);
          badge.style.display = 'none';
        };
      }
    }
  }
}

function escHtml(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
