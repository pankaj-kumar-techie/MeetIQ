# MeetIQ Core System Flow Charts

## Recording Sequence Diagram (Capture & Sync)

```mermaid
sequenceDiagram
    participant U as User
    participant E as Extension (Popup)
    participant SW as Service Worker (Background)
    participant B as Backend (FastAPI)
    participant STT as STT (Sarvam/Whisper)
    participant LLM as AI Analysis (GPT-4o)

    U->>E: Start Recording
    E->>SW: START_RECORDING (Payload)
    SW->>B: POST /api/recordings/start
    B-->>SW: 201 Created (ID)
    SW-->>E: Status: Recording
    
    loop Every 10 Seconds
        SW->>B: POST /{id}/chunk (base64 WebM)
        B-->>SW: 200 OK
    end
    
    U->>E: Stop & Analyze
    E->>SW: STOP_RECORDING
    SW->>B: POST /{id}/finalize
    B-->>SW: 202 Accepted (Processing)
    
    Note over B, STT: Background Task Starts
    B->>STT: Merge & Transcribe Audio
    STT-->>B: Full Transcript + Segments
    
    par Parallel LLM Chains
        B->>LLM: Generate Summary
        B->>LLM: Detect Commitments
        B->>LLM: Extract Action Items
        B->>LLM: Write Follow-up Email
    end
    
    B-->>SW: /status -> status: "done"
    SW->>E: ANALYSIS_DONE
    E->>U: Show Results / Alerts Sent
```

## System Deployment Overview

```mermaid
graph LR
    subgraph Client
        CE[Chrome Extension (MV3)]
        OS[Offscreen Renderer]
    end
    
    subgraph Infrastructure
        BE[FastAPI Backend]
        DB[(SQLite / Postgres)]
    end
    
    subgraph External_APIs
        OAI[OpenAI (Whisper/GPT-4o)]
        GMN[Google Gemini]
        SVA[Sarvam AI]
    end
    
    CE --> OS
    OS -- Audio Stream --> BE
    BE --> DB
    BE --> OAI
    BE --> GMN
    BE --> SVA
```
