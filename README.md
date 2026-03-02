# MeetIQ — AI Meeting Intelligence Chrome Extension

Record your browser meetings (Google Meet, Teams, Whereby), auto-transcribe with Whisper,
detect commitments and risks with GPT-4o, extract action items, generate follow-up emails,
and send automatic alerts to Discord and Slack — all in one click.

---

## What It Does

| Feature | How |
|---------|-----|
| One-click recording | Click extension → set agenda/purpose → Start |
| Records both sides | Tab audio (other people) + your mic merged into one stream |
| Auto-transcription | OpenAI Whisper — accurate, timestamps, 100+ languages |
| Commitment detection | GPT-4o finds every promise, deadline, cost mentioned |
| Action items | Structured table: Task, Owner, Deadline, Priority |
| Follow-up email | AI-written, ready to copy and send |
| Discord alerts | Rich embed with all key insights, sent on meeting end |
| Slack alerts | Block-formatted summary with commitments and actions |
| Meeting history | All past meetings stored, searchable in extension |

---

## Architecture

```
Chrome Extension (popup + offscreen recorder)
        │
        │ WebM audio chunks (base64, every 10s)
        ▼
FastAPI Backend (Railway, free tier)
        │
        ├── Transcription Provider:
        │     ├── OpenAI Whisper API (Standard)
        │     ├── Google Gemini 1.5 (Multimodal)
        │     └── Sarvam AI Saaras v3 (Focus on Indian Languages)
        │
        ├── GPT-4o-mini (×4 parallel chains)
        │     ├── Summary + sentiment
        │     ├── Commitment detector
        │     ├── Action item extractor
        │     └── Follow-up email generator
        │
        └── PostgreSQL (Railway) or SQLite (local)

Extension also fires directly:
  → Discord Webhook
  → Slack Webhook
```

---

## Deploy in 4 Steps

### Step 1 — Get an OpenAI API Key

1. Go to https://platform.openai.com/api-keys
2. Click "Create new secret key"
3. Copy it — you'll need it in Step 2

**Cost estimate:** gpt-4o-mini + Whisper ≈ $0.01–0.05 per meeting. Very cheap.

---

### Step 2 — Deploy Backend to Railway (Free)

1. Go to https://railway.app and sign up (free)
2. Click "New Project" → "Deploy from GitHub repo"
3. Fork this repo or push the `backend/` folder to a new GitHub repo
4. Railway will detect Python and deploy automatically
5. Add environment variables in Railway dashboard → Variables:
   ```
   GEMINI_API_KEY = sk-your-key-here
   GEMINI_MODEL   = gemini-1.5-flash
   
   # Or use Sarvam AI for better Indian language support:
   TRANSCRIPTION_PROVIDER = sarvam
   SARVAM_API_KEY = your-sarvam-key-here
   SARVAM_RECOGNITION_MODEL = saaras:v3
   ```
6. Click "+ New" → "Database" → "Add PostgreSQL"
   Railway sets `DATABASE_URL` automatically.
7. Copy your Railway public URL (e.g. `https://meetiq-backend.up.railway.app`)

**If you prefer local dev:**
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your OPENAI_API_KEY
uvicorn main:app --reload --port 8000
```

---

### Step 3 — Set Up Discord Webhook (takes 2 minutes)

1. Open your Discord server
2. Right-click the channel where you want alerts → Edit Channel
3. Go to Integrations → Webhooks → New Webhook
4. Give it a name (e.g. "MeetIQ") → Copy Webhook URL
5. Paste this URL into the extension Settings tab

**What you'll receive:**
```
📋 MeetIQ — Client Discovery Call Complete
Overview: Discussed AI automation requirements...

🔑 Key Points
• Client needs voice agent for inbound calls
• Budget: $3-5k range mentioned
• Timeline: 6 weeks preferred

⚠️ Commitments (3)
  HIGH  "We will deliver the first version in 2 weeks"
  MED   "That will cost around $4,000"
  LOW   "I'll send you the requirements doc tomorrow"

✅ Action Items (4)
• Send proposal draft — Team (by Friday)
• Share API documentation — Client (Not specified)
...
```

---

### Step 4 — Set Up Slack Webhook (takes 2 minutes)

1. Go to https://api.slack.com/apps → Create New App → From scratch
2. Name it "MeetIQ" → select your workspace
3. Go to Incoming Webhooks → Activate → Add New Webhook to Workspace
4. Choose a channel → Allow → Copy Webhook URL
5. Paste into extension Settings tab

---

### Step 5 — Install the Chrome Extension

1. Open Chrome → go to `chrome://extensions/`
2. Enable "Developer mode" (top right toggle)
3. Click "Load unpacked"
4. Select the `extension/` folder from this repo
5. The MeetIQ icon appears in your toolbar

**First time setup:**
1. Click the extension icon
2. Go to Settings tab
3. Paste your:
   - Discord webhook URL
   - Slack webhook URL  
   - Backend API URL (your Railway URL from Step 2)
4. Click Save Settings

---

## Usage

### Starting a Meeting

1. Open Google Meet / Teams / Whereby in your browser
2. Click the MeetIQ extension icon
3. Extension auto-detects the platform (green banner appears)
4. Fill in:
   - **Meeting Name** (auto-filled from tab title)
   - **Purpose** — why is this meeting happening?
   - **Agenda** — what topics will you cover?
   - **Participants** — comma-separated names
   - **Meeting Type** — Discovery, Sales, Interview, etc.
5. Click **Start Recording**
6. Chrome will ask for microphone permission — Allow

### During the Meeting

- Red pulsing dot shows recording is active
- Timer counts up
- Participant names are auto-detected from the meeting UI
- Nothing else to do — just have your meeting normally

### After the Meeting

1. Click **Stop & Analyze**
2. Extension shows processing steps (takes 30–90 seconds depending on length)
3. Results appear:
   - Commitments count with risk levels
   - Action items count
   - Open questions count
   - Discord ✓ / Slack ✓ badges confirming alerts sent
4. Click "Copy Follow-up Email" to grab the draft

---

## File Structure

```
meetiq/
├── extension/                # Chrome extension
│   ├── manifest.json         # Extension config + permissions
│   ├── background/
│   │   ├── sw.js             # Service worker (main controller)
│   │   ├── store.js          # chrome.storage wrapper
│   │   └── api.js            # Backend API client + Discord/Slack
│   ├── offscreen/
│   │   ├── recorder.html     # Required by Chrome for audio capture
│   │   └── recorder.js       # Tab + mic merge via Web Audio API
│   ├── content/
│   │   └── detector.js       # Auto-detect platform + participants
│   ├── popup/
│   │   ├── popup.html        # Extension UI
│   │   ├── popup.css         # Dark theme UI styles
│   │   └── popup.js          # UI controller + state management
│   └── assets/               # Add icon16.png, icon48.png, icon128.png
│
└── backend/                  # FastAPI on Railway
    ├── main.py               # App entry + CORS
    ├── requirements.txt
    ├── Procfile              # Railway start command
    ├── core/
    │   └── database.py       # SQLAlchemy async engine
    ├── models/
    │   └── recording.py      # Recording + Chunk + Analysis tables
    ├── routers/
    │   ├── recordings.py     # /start, /chunk, /finalize, /status
    │   └── meetings.py       # /list, /get, /delete
    └── services/
        ├── transcription.py  # Whisper API integration
        └── ai_analysis.py    # 4 parallel GPT-4o chains
```

---

## Icons Needed

You need to add 3 PNG icons to `extension/assets/`:
- `icon16.png`  — 16×16px
- `icon48.png`  — 48×48px  
- `icon128.png` — 128×128px

Simple way: Go to https://www.favicon.io/favicon-generator/
Type "M", pick a dark blue background (#1A4F8A), white text.
Download and resize to the 3 sizes above.

---

## Local Development

**Backend:**
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # Add your OPENAI_API_KEY
uvicorn main:app --reload
# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

**Extension:**
1. Load `extension/` as unpacked in Chrome
2. Set API URL to `http://localhost:8000` in Settings tab

---

## Upgrading to Better Quality

**Switch to GPT-4o** (2x better quality, 10x the cost):
```
# In Railway Variables:
OPENAI_MODEL = gpt-4o
```

**Add speaker diarization** (tell who said what):
In `backend/services/transcription.py` replace the Whisper call with
pyannote.audio or AssemblyAI which supports multi-speaker detection.

**Add more alert destinations:**
In `extension/background/api.js` add new `send*Alert` functions for
Telegram, email, or any webhook-based service.

---

## Cost Estimate (Monthly)

| Usage | Cost |
|-------|------|
| 10 meetings/month, 30min each | ~$0.50 |
| 50 meetings/month, 45min each | ~$3.00 |
| Railway backend (free tier)   | $0 |
| Railway PostgreSQL (free tier)| $0 |

Whisper: $0.006/minute. GPT-4o-mini: ~$0.01/meeting.

---

## Troubleshooting

**"Tab capture returned null stream"**
→ Make sure you're on a meeting tab (not the extension settings).
→ Chrome blocks tab capture on `chrome://` pages.

**"No speech detected"**
→ Check your microphone is working.
→ Ensure the meeting has actual audio playing in the tab.

**Discord alert not sending**
→ Verify webhook URL starts with `https://discord.com/api/webhooks/`
→ Test it: paste URL in browser, you should see `{"message": "Method Not Allowed"}`

**Backend 500 errors**
→ Check Railway logs for the actual error.
→ Most common: missing OPENAI_API_KEY env variable.

**Extension not updating after code changes**
→ Go to `chrome://extensions/` → click the refresh icon on MeetIQ.
