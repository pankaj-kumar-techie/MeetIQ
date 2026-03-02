import os, base64, tempfile, asyncio
import google.generativeai as genai

GEMINI_KEY   = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

SARVAM_KEY   = os.getenv("SARVAM_API_KEY", "")
SARVAM_MODEL = os.getenv("SARVAM_RECOGNITION_MODEL", "saaras:v3")

TRANSCRIPTION_PROVIDER = os.getenv("TRANSCRIPTION_PROVIDER", "gemini") # "gemini" or "sarvam"

genai.configure(api_key=GEMINI_KEY)
_model = genai.GenerativeModel(GEMINI_MODEL)


async def transcribe_chunks(chunks_b64: list[str]) -> dict:
    """
    Merge base64 WebM chunks into a single file, send to a provider for transcription.
    For Sarvam, we split into 20s windows to bypass their 30s duration limit.
    Returns: { full_text, segments: [{start, end, text, speaker}] }
    """
    import time
    start_total = time.time()
    
    if not chunks_b64:
        return {"full_text": "", "segments": []}

    if TRANSCRIPTION_PROVIDER.lower() == "sarvam":
        # Strategy: Sarvam has a 30s limit. We group chunks (each ~10s) into windows of 2.
        window_size = 2 
        all_text = []
        all_segments = []
        
        print(f"[TIMING] Sarvam Windowed STT: Processing {len(chunks_b64)} chunks in windows of {window_size}...")
        
        for i in range(0, len(chunks_b64), window_size):
            window = chunks_b64[i : i + window_size]
            window_raw = b"".join(base64.b64decode(c) for c in window)
            
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
                f.write(window_raw)
                tmp_path = f.name
            
            try:
                print(f"[TIMING] Transcribing window {i//window_size + 1}...")
                res = await _sarvam_transcribe(tmp_path)
                all_text.append(res["full_text"])
                # Offset segments by the window start time (approx 10s per chunk)
                offset = i * 10 
                for seg in res["segments"]:
                    seg["start"] += offset
                    seg["end"] += offset
                    all_segments.append(seg)
            finally:
                try: os.unlink(tmp_path)
                except: pass
        
        return {
            "full_text": " ".join(all_text),
            "segments": all_segments
        }

    # Default logic (Gemini) - handles long files natively
    print(f"[TIMING] Merging {len(chunks_b64)} chunks for {TRANSCRIPTION_PROVIDER}...")
    raw_bytes = b"".join(base64.b64decode(c) for c in chunks_b64)

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(raw_bytes)
        tmp_path = f.name

    try:
        start_stt = time.time()
        print(f"[TIMING] Starting transcription via {TRANSCRIPTION_PROVIDER}...")
        res = await _gemini_transcribe(tmp_path)
        print(f"[TIMING] Transcription took {time.time() - start_stt:.2f}s")
        return res
    except Exception as e:
        print(f"[MeetIQ] Transcription ERROR via {TRANSCRIPTION_PROVIDER}: {e}")
        raise e
    finally:
        try: os.unlink(tmp_path)
        except: pass
        print(f"[TIMING] Total finalize-transcribe phase: {time.time() - start_total:.2f}s")


async def _gemini_transcribe(file_path: str) -> dict:
    """Upload audio to Gemini Files API and transcribe with timestamps."""
    if not GEMINI_KEY or "your-gemini-api-key" in GEMINI_KEY:
        raise Exception("GEMINI_API_KEY is not set or is still a placeholder. Please set it in your .env file.")

    loop = asyncio.get_event_loop()

    # 1. Upload file to Gemini Files API
    uploaded = await loop.run_in_executor(None, lambda: genai.upload_file(
        path=file_path,
        mime_type="audio/webm",
    ))

    # 1b. Polling: wait for file to be processed (Active)
    import time
    start_wait = time.time()
    while uploaded.state.name == "PROCESSING":
        if time.time() - start_wait > 60:
            raise Exception("Gemini file processing timed out")
        await asyncio.sleep(2) # Non-blocking sleep
        uploaded = await loop.run_in_executor(None, lambda: genai.get_file(uploaded.name))

    if uploaded.state.name != "ACTIVE":
        raise Exception(f"Gemini file failed to process: {uploaded.state.name}")

    def _do_transcribe():
        # 2. Ask Gemini to transcribe with approximate timestamps
        response = _model.generate_content(
            [
                uploaded,
                """Transcribe this meeting audio accurately and completely.
Return ONLY a JSON object in this exact format (no markdown, no extra text):
{
  "full_text": "complete transcript of everything said",
  "segments": [
    {"start": 0.0, "end": 5.2, "text": "what was said", "speaker": "Speaker 1"},
    {"start": 5.5, "end": 10.0, "text": "response", "speaker": "Speaker 2"}
  ]
}
Rules:
- Capture every word spoken, even filler words if important
- Estimate timestamps in seconds from the start
- Label speakers as Speaker 1, Speaker 2, etc.
- If only one speaker, use 'Speaker 1' throughout
- Return valid JSON only""",
            ],
            generation_config=genai.types.GenerationConfig(
                temperature=0.0,
                max_output_tokens=8192,
                response_mime_type="application/json",
            ),
        )

        # 3. Clean up uploaded file from Gemini storage
        try:
            genai.delete_file(uploaded.name)
        except Exception:
            pass

        return response.text.strip()

    import json
    raw = await loop.run_in_executor(None, _do_transcribe)

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: treat entire response as plain text
        return {"full_text": raw, "segments": []}

    return {
        "full_text": data.get("full_text", "").strip(),
        "segments":  data.get("segments", []),
    }


async def _sarvam_transcribe(file_path: str) -> dict:
    """Send audio to Sarvam AI STT for transcription."""
    if not SARVAM_KEY:
        raise Exception("SARVAM_API_KEY is not set. Please set it in your .env file.")

    loop = asyncio.get_event_loop()

    def _do_sarvam_transcribe():
        from sarvamai import SarvamAI
        # Check if key is leaked/invalid
        if not SARVAM_KEY or len(SARVAM_KEY) < 20:
             raise Exception("Invalid SARVAM_API_KEY. Please update .env")
             
        client = SarvamAI(api_subscription_key=SARVAM_KEY)
        
        # sarvamai SDK uses 'speech_to_text' or similar. 
        # According to logs, it raised BadRequestError.
        try:
             with open(file_path, "rb") as f:
                 response = client.speech_to_text.transcribe(
                     file=f,
                     model=SARVAM_MODEL,
                     mode="transcribe",
                     with_timestamps=True  # 🚀 Added from newest docs
                 )
             return response
        except Exception as stt_err:
             print(f"[Sarvam STT Error] {stt_err}")
             # Re-raise with more detail if possible
             if hasattr(stt_err, "response") and hasattr(stt_err.response, "text"):
                 print(f"[Sarvam Detail] {stt_err.response.text}")
             raise stt_err

    res = await loop.run_in_executor(None, _do_sarvam_transcribe)

    # 🚀 Professional Parsing for Saaras v3 results
    full_text = ""
    segments = []
    
    # Extract transcript string safely
    if isinstance(res, dict):
        full_text = res.get("transcript", "")
        # Extract word-level segments
        ts_data = res.get("timestamps")
        if ts_data and isinstance(ts_data, dict):
            words = ts_data.get("words", [])
            # Group words into logical segments (~12 words each) for cleaner Chat UI
            for i in range(0, len(words), 12):
                chunk = words[i : i + 12]
                if chunk:
                    txt = " ".join([w.get("word", "") for w in chunk])
                    start = float(chunk[0].get("start_time_seconds") or 0)
                    end = float(chunk[-1].get("end_time_seconds") or 0)
                    segments.append({
                        "start": start,
                        "end": end,
                        "text": txt,
                        "speaker": "Speaker 1"
                    })
    elif hasattr(res, "transcript"):
        full_text = res.transcript
        # Try to handle object-style timestamps if any
        if hasattr(res, "timestamps") and res.timestamps:
            # same logic for objects...
            pass

    # Safety: fallback if no segments were parsed
    if not segments:
        segments = [{
            "start": 0.0,
            "end": 0.0,
            "text": full_text.strip(),
            "speaker": "Speaker 1"
        }]

    return {
        "full_text": full_text.strip(),
        "segments": segments
    }
