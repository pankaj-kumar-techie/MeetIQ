import { MeetingStore } from './store.js'
import { uploadChunk, sendAlert } from './api.js'

const store = new MeetingStore()

// ─── Initialize: Resume any pending tasks on SW start ──────────────────────────
async function initialize() {
  await store.ensureLoaded();
  const meeting = store.getActiveMeeting();
  if (meeting && meeting.status === 'processing') {
    console.log('[sw] Resuming analysis for meeting:', meeting.id);
    handleRecordingComplete({ type: 'RESUME_POLLING' }).catch(console.error);
  }
}
initialize();

// ─── Message Router ────────────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  ; (async () => {
    await store.ensureLoaded();

    try {
      switch (msg.type) {
        case 'START_RECORDING': reply(await startRecording(msg.payload)); break
        case 'STOP_RECORDING': reply(await stopRecording()); break
        case 'RESET_STATE':
          await store.clearActiveMeeting();
          chrome.action.setBadgeText({ text: '' });
          reply({ ok: true });
          break;
        case 'REMOTE_LOG':
          await remoteLog(msg.level, msg.tag, msg.message);
          reply({ ok: true });
          break;
        case 'GET_STATE': reply(store.getState()); break
        case 'MEETING_DETECTED': handleMeetingDetected(msg.payload, sender); reply({ ok: true }); break
        case 'MEETING_TYPE_HINT': handleMeetingTypeHint(msg.payload); reply({ ok: true }); break
        case 'AUDIO_CHUNK':
          console.log('[sw] Received AUDIO_CHUNK');
          await handleAudioChunk(msg.chunk);
          reply({ ok: true });
          break;
        case 'GET_MEETINGS': reply(await store.getAllMeetings()); break
        case 'DELETE_MEETING': reply(await store.deleteMeeting(msg.id)); break
        case 'RECORDING_COMPLETE': handleRecordingComplete(msg); reply({ ok: true }); break
        default: reply({ error: 'Unknown message type' })
      }
    } catch (err) {
      console.error('[sw] Router error:', err);
      try { reply({ ok: false, error: err.message }); } catch (e) { }
    }
  })()
  return true
})

// ─── Start Recording ───────────────────────────────────────────────────────────
async function startRecording({ name, agenda, purpose, participants, meetingType }) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
    if (!tab?.id) return { ok: false, error: 'No active tab found' }

    // ── Register with backend ──────────────────────────────────────────────────
    const base = await getApiBase()
    const res = await fetch(`${base}/api/recordings/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        purpose: purpose || '',
        agenda: agenda || '',
        participants: Array.isArray(participants) ? participants : [],
        meeting_type: meetingType || 'discovery',
        platform: detectPlatformFromUrl(tab.url),
      }),
    })

    if (!res.ok) {
      const txt = await res.text()
      return { ok: false, error: `Backend error ${res.status}: ${txt.slice(0, 120)}` }
    }

    const { recording_id } = await res.json()
    await remoteLog('info', 'sw', `Recording started: ${recording_id}`);

    await store.setActiveMeeting({
      id: recording_id,
      name,
      agenda,
      purpose,
      participants: participants || [],
      meetingType: meetingType || 'discovery',
      startedAt: Date.now(),
      status: 'recording',
    })

    // ── Start offscreen audio capture ──────────────────────────────────────────
    await ensureOffscreen()

    // Get tabCapture stream ID first (must be called from background)
    const streamId = await new Promise((resolve, reject) => {
      chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id }, (id) => {
        if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message))
        else resolve(id)
      })
    })

    const { settings = {} } = await chrome.storage.local.get('settings')

    // Route to offscreen document (must include target:'offscreen')
    chrome.runtime.sendMessage({
      type: 'START_RECORDING',
      target: 'offscreen',
      streamId,
      speakerName: settings.speakerName || 'Me',
    })

    chrome.alarms.create('meetiq_tick', { periodInMinutes: 1 })
    chrome.action.setBadgeText({ text: '●' })
    chrome.action.setBadgeBackgroundColor({ color: '#ef4444' })

    return { ok: true, meetingId: recording_id }
  } catch (err) {
    console.error('[MeetIQ start]', err)
    return { ok: false, error: err.message }
  }
}

// ─── Stop Recording ────────────────────────────────────────────────────────────
async function stopRecording() {
  try {
    const meeting = store.getActiveMeeting()
    if (!meeting) return { ok: false, error: 'No active meeting' }

    // If meeting failed, just clear it and reset UI
    if (meeting.status === 'error') {
      await store.clearActiveMeeting()
      chrome.action.setBadgeText({ text: '' })
      return { ok: true }
    }

    // Tell offscreen to stop — it will fire RECORDING_COMPLETE when done
    chrome.runtime.sendMessage({ type: 'STOP_RECORDING', target: 'offscreen' }).catch(() => { })
    chrome.alarms.clear('meetiq_tick')
    chrome.action.setBadgeText({ text: '' })

    await store.updateActiveMeeting({ status: 'processing', endedAt: Date.now() })

    return { ok: true }
  } catch (err) {
    return { ok: false, error: err.message }
  }
}

// ─── Called when offscreen recorder finishes (all chunks collected) ────────────
async function handleRecordingComplete(msg) {
  const meeting = store.getActiveMeeting()
  if (!meeting) return

  try {
    // 1. Finalize via backend
    const base = await getApiBase()
    await remoteLog('info', 'sw', `Finalizing ${meeting.id}`);
    const res = await fetch(`${base}/api/recordings/${meeting.id}/finalize`, { method: 'POST' })
    if (!res.ok) throw new Error(`Finalize failed: ${res.status}`)

    // 2. Poll until done
    await remoteLog('info', 'sw', `Polling ${meeting.id}`);
    const result = await pollUntilDone(meeting.id, base)

    // 4. Store result
    await remoteLog('info', 'sw', `Result received for ${meeting.id}`);
    await store.setMeetingResult(meeting.id, { ...result, meetingName: meeting.name })

    // 5. Broadcast completion
    chrome.runtime.sendMessage({ type: 'ANALYSIS_DONE', meetingId: meeting.id }).catch(() => { })

    // 6. Clear active state
    await store.clearActiveMeeting()
    await remoteLog('info', 'sw', 'Meeting cleared from state');

    // 7. Show notification
    chrome.notifications.create({
      type: 'basic',
      iconUrl: chrome.runtime.getURL('assets/icon128.png'),
      title: 'MeetIQ — Analysis Complete',
      message: `Summary: ${result.summary?.overview?.slice(0, 100) || 'Your meeting summary is ready.'}`,
    })

  } catch (err) {
    console.error('[MeetIQ finalize]', err)
    if (meeting?.id) {
      await store.updateActiveMeeting({ status: 'error' })
      // Even on error, we might want to clear it after a delay or just leave it for user to see
    }
  }
}

// ─── Poll /status until done ───────────────────────────────────────────────────
async function pollUntilDone(recordingId, base, maxWait = 300_000) {
  const start = Date.now();
  let failCount = 0;

  while (Date.now() - start < maxWait) {
    await new Promise(r => setTimeout(r, 2500));

    try {
      const res = await fetch(`${base}/api/recordings/${recordingId}/status`);
      if (!res.ok) {
        if (res.status === 404) throw new Error('Recording lost on server');
        throw new Error(`HTTP ${res.status}`);
      }

      const data = await res.json();
      failCount = 0; // Reset on success

      if (data.status === 'done') return data;
      if (data.status === 'error') throw new Error('Analysis failed on server');
    } catch (err) {
      failCount++;
      console.warn(`[sw] Poll attempt failed (${failCount}):`, err.message);

      // If we fail 5 times in a row, the server is truly down
      if (failCount > 5) throw err;

      // Wait extra if failing
      await new Promise(r => setTimeout(r, 2000 * failCount));
    }
  }
  throw new Error('Analysis timed out');
}

// ─── Handle incoming audio chunk (streamed every 10s) ─────────────────────────
async function handleAudioChunk(base64Chunk) {
  const meeting = store.getActiveMeeting()
  if (!meeting) {
    console.warn('[sw] AUDIO_CHUNK received but no active meeting');
    return;
  }
  if (meeting.status !== 'recording' && meeting.status !== 'processing') {
    console.warn('[sw] AUDIO_CHUNK received but meeting status is', meeting.status);
    return;
  }

  try {
    console.log('[sw] Uploading chunk for meeting', meeting.id);
    await uploadChunk(meeting.id, base64Chunk);
  } catch (err) {
    console.error('[sw] Chunk upload failed:', err.message);
  }
}

// ─── Meeting detected from content script ────────────────────────────────────
function handleMeetingDetected({ platform }, sender) {
  chrome.action.setBadgeText({ text: '●', tabId: sender.tab?.id })
  chrome.action.setBadgeBackgroundColor({ color: '#22c55e' })
}

// ─── Meeting type hint from content script ────────────────────────────────────
function handleMeetingTypeHint({ suggestedType, confidence, signals }) {
  // Store the hint so popup can read it when it opens
  chrome.storage.session.set({
    meetingTypeHint: { suggestedType, confidence, signals, ts: Date.now() }
  }).catch(() => {
    // session storage not available in older Chrome versions — use local
    chrome.storage.local.set({
      meetingTypeHint: { suggestedType, confidence, signals, ts: Date.now() }
    })
  })
}

async function remoteLog(level, tag, message) {
  try {
    const base = await getApiBase();
    await fetch(`${base}/api/recordings/debug/log`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ level, tag, message: String(message) })
    }).catch(() => { });
  } catch (e) { }
}

// ─── Alarms — keep duration live ─────────────────────────────────────────────
chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === 'meetiq_tick') {
    const m = store.getActiveMeeting()
    if (m) store.updateActiveMeeting({ duration: Date.now() - m.startedAt })
  }
})

// ─── Helpers ──────────────────────────────────────────────────────────────────
async function ensureOffscreen() {
  try {
    const hasDoc = await chrome.offscreen.hasDocument()
    if (!hasDoc) {
      await chrome.offscreen.createDocument({
        url: 'offscreen/recorder.html',
        reasons: ['USER_MEDIA', 'DISPLAY_MEDIA'],
        justification: 'Capture tab audio and microphone for meeting transcription',
      })
    }
  } catch (e) { console.warn('[MeetIQ offscreen]', e) }
}

async function getApiBase() {
  const { settings = {} } = await chrome.storage.local.get('settings')
  return settings.apiUrl || 'http://localhost:8000'
}

function detectPlatformFromUrl(url = '') {
  if (url.includes('meet.google.com')) return 'google-meet'
  if (url.includes('teams.microsoft.com')) return 'teams'
  if (url.includes('whereby.com')) return 'whereby'
  if (url.includes('zoom.us')) return 'zoom'
  return 'unknown'
}
