# MeetIQ — Developer Setup Guide

## Prerequisites

| Tool | Version |
|------|---------|
| Docker Desktop | ≥ 4.x |
| Google Chrome | ≥ 114 |
| A Gemini API key | Free tier (aistudio.google.com) |

---

## Step 1 — Configure the Backend

```bash
cd d:\workspace\MeetIQ\backend
```

Open `.env` and set your Gemini key:

```env
GEMINI_API_KEY=your-real-key-from-ai-studio
GEMINI_MODEL=gemini-1.5-flash
```

> **Note:** For local dev the database defaults to SQLite (`meetiq.db` inside a Docker volume). No database setup needed.

---

## Step 2 — Start the Backend with Docker

```bash
# From d:\workspace\MeetIQ\backend
docker compose up --build
```

Expected output (first run ~60s):
```
meetiq-api  | INFO:     Application startup complete.
meetiq-api  | INFO:     Uvicorn running on http://0.0.0.0:8000
```

Verify it's running:
```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

To stop: `docker compose down`

---

## Step 3 — Load the Extension in Chrome Developer Mode

1. Open Chrome and navigate to: `chrome://extensions`
2. Toggle **Developer mode** ON (top-right switch)
3. Click **"Load unpacked"**
4. Select the folder: `d:\workspace\MeetIQ\extension`
5. The **MeetIQ** extension icon will appear in your toolbar

> **Tip:** Pin it to the toolbar by clicking the puzzle-piece icon → pin MeetIQ.

---

## Step 4 — Configure the Extension

1. Click the MeetIQ icon in the toolbar
2. Go to **⚙ Settings** tab
3. Set **API Endpoint** to: `http://localhost:8000`
4. Optionally add Discord/Slack webhook URLs
5. Click **Save Settings**

---

## Step 5 — Test Auto Meeting Type Detection

1. Navigate to **https://meet.google.com** (you don't need to join a call)
2. Click the MeetIQ icon
3. After ~2 seconds a chip should auto-select (e.g. "Discovery") with an **"✦ Auto-detected"** badge
4. You can manually override by clicking any other chip

---

## Step 6 — Test a Recording

1. Join or start a real Google Meet, Teams, or Whereby call
2. Click MeetIQ → fill in meeting name → click **Start Recording**
3. Speak for 30+ seconds ("I will send the proposal by Friday, fixed at $5000")
4. Click **Stop Recording**
5. The status bar shows "Analyzing meeting…"
6. Once done, go to **Meetings** tab — you'll see:
   - Meeting type (auto-detected by AI)
   - ⚠️ Commitment count badge (Promises/Commitments)
   - ✅ Action item count

---

## Architecture Overview

```
Chrome Extension                     Docker Backend (port 8000)
─────────────────                    ──────────────────────────
content/detector.js  ──MEETING_TYPE_HINT──►  (stored in session)
popup/popup.js       ──START_RECORDING──►  /api/recordings/start
background/sw.js     ──tabCapture───►     offscreen/recorder.js
                     ──AUDIO_CHUNK──►  /api/recordings/{id}/chunk
                     ──finalize─────►  /api/recordings/{id}/finalize
                     ◄──poll─────────  /api/recordings/{id}/status
                                           ↓
                                       Gemini 1.5 Flash (transcription)
                                       Gemini 1.5 Flash (analysis)
                                       → commitments, actions, type
```

---

## Reloading After Code Changes

**Backend:** Changes auto-reload (source is bind-mounted into Docker).

**Extension:** Go to `chrome://extensions` → click the **↺ refresh** icon on MeetIQ.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "No active tab found" | Make sure you're on a Google Meet / Teams / Whereby / Zoom tab |
| "Backend error 422" | Check field names in request payload (see sw.js) |
| Extension doesn't auto-detect type | Wait 2–6 seconds after tab loads; check console for `MEETING_TYPE_HINT` |
| Docker build fails | Run `docker compose down -v` then `docker compose up --build` again |
| SQLite locked | Stop and restart Docker: `docker compose restart` |
