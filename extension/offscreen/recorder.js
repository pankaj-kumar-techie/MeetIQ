// offscreen.js — Runs in offscreen document (MV3)
// Mixes: tab audio (both speakers via tabCapture) + user mic
// Uses AudioContext to merge streams before MediaRecorder

let mediaRecorder = null;
let chunks = [];
let audioContext = null;
let micStream = null;
let tabStream = null;
let destination = null;
let speakerName = 'Me';

async function log(msg) {
  console.log('[recorder]', msg);
  chrome.runtime.sendMessage({ type: 'REMOTE_LOG', level: 'info', tag: 'recorder', message: msg }).catch(() => { });
}
async function warn(msg) {
  console.warn('[recorder]', msg);
  chrome.runtime.sendMessage({ type: 'REMOTE_LOG', level: 'warn', tag: 'recorder', message: msg }).catch(() => { });
}
async function error(msg) {
  console.error('[recorder]', msg);
  chrome.runtime.sendMessage({ type: 'REMOTE_LOG', level: 'error', tag: 'recorder', message: msg }).catch(() => { });
}

// ─── Message handler ───────────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.target !== 'offscreen') return;

  switch (msg.type) {
    case 'START_RECORDING':
      startRecording(msg.streamId, msg.speakerName).then(sendResponse);
      return true;

    case 'STOP_RECORDING':
      stopRecording().then(sendResponse);
      return true;
  }
});

// ─── Start: get mic + tab stream, mix via AudioContext ─────────────────────────
async function startRecording(streamId, name) {
  speakerName = name || 'Me';
  chunks = [];

  try {
    await log(`Starting capture: streamId=${streamId.slice(0, 8)}...`);

    // 1. Get tab audio using stream ID from tabCapture
    tabStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        mandatory: {
          chromeMediaSource: 'tab',
          chromeMediaSourceId: streamId,
        },
      },
      video: false,
    });
    await log(`Tab stream obtained: ${tabStream.getAudioTracks().length} tracks`);

    // 2. Get user mic
    await log('Starting mic capture...');
    const mStream = await navigator.mediaDevices.getUserMedia({ audio: true })
      .catch(async e => {
        await error(`Mic capture failed: ${e.message}`);
        throw e;
      });

    await log('Mic stream obtained: ' + mStream.getTracks().length + ' tracks');
    micStream = mStream;

    // 3. Mix both streams via AudioContext
    audioContext = new AudioContext({ sampleRate: 16000 });
    destination = audioContext.createMediaStreamDestination();

    const tabSource = audioContext.createMediaStreamSource(tabStream);
    const micSource = audioContext.createMediaStreamSource(micStream);

    await log(`Streams obtained. Tab tracks: ${tabStream.getAudioTracks().length} Mic tracks: ${micStream.getAudioTracks().length}`);

    if (audioContext.state === 'suspended') {
      await audioContext.resume();
      await log('AudioContext resumed');
    }

    // Tab audio: full volume (remote speakers)
    const tabGain = audioContext.createGain();
    tabGain.gain.value = 1.0;
    tabSource.connect(tabGain);
    tabGain.connect(destination);

    // Mic audio: slightly boosted (local speaker = you)
    const micGain = audioContext.createGain();
    micGain.gain.value = 1.2;
    micSource.connect(micGain);
    micGain.connect(destination);

    // 4. Record the mixed stream
    mediaRecorder = new MediaRecorder(destination.stream, {
      mimeType: 'audio/webm;codecs=opus',
      audioBitsPerSecond: 128000,
    });
    await log(`MediaRecorder created. Mime: ${mediaRecorder.mimeType}`);

    let localChunks = [];
    mediaRecorder.ondataavailable = async (e) => {
      if (e.data && e.data.size > 0) {
        chunks.push(e.data);
        localChunks.push(e.data);
      }

      // Stream chunks every ~2.5 seconds (lower threshold for debugging)
      if (localChunks.length >= 10) {
        const blob = new Blob(localChunks, { type: 'audio/webm' });
        localChunks = [];
        const reader = new FileReader();
        reader.onloadend = async () => {
          await log('[recorder] Dispatching chunk to background');
          chrome.runtime.sendMessage({
            type: 'AUDIO_CHUNK',
            chunk: reader.result.split(',')[1],
          }).catch(e => error(`Send chunk error: ${e.message}`));
        };
        reader.readAsDataURL(blob);
      }
    };

    mediaRecorder.onstop = async () => {
      await log('MediaRecorder stopped. Finalizing...');
      // 1. Send any remaining small chunks
      if (localChunks.length > 0) {
        const blob = new Blob(localChunks, { type: 'audio/webm' });
        const base64 = await new Promise(resolve => {
          const reader = new FileReader();
          reader.onloadend = () => resolve(reader.result.split(',')[1]);
          reader.readAsDataURL(blob);
        });
        await chrome.runtime.sendMessage({ type: 'AUDIO_CHUNK', chunk: base64 });
        await log('Sent final remaining chunk');
      }

      // 2. Signal recording is complete
      chrome.runtime.sendMessage({
        type: 'RECORDING_COMPLETE',
        duration: Math.floor(chunks.length * 250 / 1000),
      });
      await log('RECORDING_COMPLETE signaled');

      cleanup();
    };

    // Collect chunks every 250ms
    mediaRecorder.start(250);
    await log('MediaRecorder started');

    return { ok: true };
  } catch (err) {
    await error(`startRecording failed: ${err.message}`);
    cleanup();
    return { ok: false, error: err.message };
  }
}

async function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
    await log('stopRecording() called');
  }
  return { ok: true };
}

function cleanup() {
  if (audioContext) { audioContext.close(); audioContext = null; }
  if (micStream) { micStream.getTracks().forEach(t => t.stop()); micStream = null; }
  if (tabStream) { tabStream.getTracks().forEach(t => t.stop()); tabStream = null; }
  mediaRecorder = null;
  chunks = [];
  console.log('[recorder] Cleanup complete');
}
