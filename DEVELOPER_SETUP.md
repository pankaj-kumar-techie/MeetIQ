# 🛠️ MeetIQ — Technical Developer Guide

Welcome to the MeetIQ development environment. This guide covers the end-to-end setup for the browser extension and the Docker-based FastAPI intelligence engine.

---

## 📋 System Prerequisites
| Requirement | Detail |
| :--- | :--- |
| **OS** | Windows (PowerShell/WSL2), macOS, or Linux |
| **Runtime** | Docker Desktop & Docker Compose (V2+) |
| **Browser** | Google Chrome (Standard or Canary) for MV3 support |
| **API Keys** | Sarvam AI (STT/Brain), OpenRouter, or Gemini |

---

## 🏗️ Step 1: Intelligence Engine (Backend)

The backend is a high-performance **FastAPI** application served via **Uvicorn** and orchestrated with **Docker**.

### Configuration
Go to the `backend` directory and configure your environment:
```powershell
cp .env.example .env
```
Key variables to set:
- `AI_PROVIDER`: `sarvam`, `openrouter`, or `gemini`.
- `SARVAM_API_KEY`: Required for high-accuracy Indian language STT.

### Launching with Docker
```powershell
docker-compose up -d --build
```

**Diagnostic Check:**
```powershell
# Check health
curl http://localhost:8000/health
# Check performance logs
docker logs meetiq-api --tail 20
```

---

## 🧩 Step 2: Browser Extension (Frontend)

The extension uses **Manifest V3** and handles audio capture through an **Offscreen Document** for security and stability.

### Installation
1. Navigate to: `chrome://extensions`
2. Enable **Developer mode** (Top Right).
3. Click **Load unpacked**.
4. Select the project `extension/` directory.

### Initial Tuning
1. Click the MeetIQ icon → **Settings**.
2. Set **Server URL** to `http://localhost:8000`.
3. Enter your **Speaker Name** (used to color chat bubbles in the dashboard).

---

## 🚦 Testing the Intelligence Flow

A successful test run typically follows this sequence of events in the logs:

1. **Start**: Popup sends meeting metadata.
2. **Streaming**: Extension sends 10s base64 chunks to `/chunk`.
3. **Transcription**: On `Stop`, backend runs windows of 20s through **Sarvam Saaras v3**.
4. **Manual Analysis**: Open the dashboard, review the transcript, and click **✨ Run AI Brain**.

---

## 📂 Key Architecture Modules

### `backend/services/transcription.py`
Contains the **Smart Windowing** logic that splits audio into 20s segments to bypass provider limits while maintaining sub-second transcription latency.

### `backend/services/ai_analysis.py`
The "Master Brain" logic. It uses **Single-Pass Prompting** to extract summaries, follow-ups, and commitments in a single LLM call, reducing token costs by ~75%.

### `extension/offscreen/recorder.js`
The core audio engine. It uses the `tabCapture` and `navigator.mediaDevices` APIs to merge system audio and microphone into a single high-fidelity WebM stream.

---

## 🆘 Troubleshooting & Debugging

| Problem | Root Cause | Fix |
| :--- | :--- | :--- |
| **Diarization Error** | Sarvam REST API failure. | Check `SARVAM_API_KEY` in `.env`. |
| **Looping finalized** | Extension polling timeout. | Check `docker logs` for STT hanging. |
| **No "Run Brain" button** | JSON Summarization was already attempted. | Delete the meeting and re-record. |
| **Missing Segments** | STT returned a flat string. | Ensure `with_timestamps=true` is enabling word-level data. |

---

Developed for **MeetIQ** — Empowering meetings with localized AI.
