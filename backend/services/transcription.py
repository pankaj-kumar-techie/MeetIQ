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
    Merge base64 WebM chunks into a single file, send to Gemini for transcription.
    Returns: { full_text, segments: [{start, end, text, speaker}] }
    """
    if not chunks_b64:
        return {"full_text": "", "segments": []}

    raw_bytes = b"".join(base64.b64decode(c) for c in chunks_b64)

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(raw_bytes)
        tmp_path = f.name

    try:
        if TRANSCRIPTION_PROVIDER == "sarvam":
            return await _sarvam_transcribe(tmp_path)
        else:
            return await _gemini_transcribe(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


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
        client = SarvamAI(api_subscription_key=SARVAM_KEY)
        
        # Sarvam SDK returns response with "transcript"
        with open(file_path, "rb") as f:
            response = client.speech_to_text.transcribe(
                file=f,
                model=SARVAM_MODEL,
                mode="transcribe"
            )
        return response

    res = await loop.run_in_executor(None, _do_sarvam_transcribe)

    # Assuming Sarvam response structure has 'transcript' or similar
    # According to Sarvam docs, the response is often a dictionary containing "transcript"
    # and maybe segments if diarization is enabled (not enabled here)
    transcript = res.get("transcript", "") if isinstance(res, dict) else str(res)
    
    # MeetIQ expects segments, we'll provide a single segment if no others provided
    return {
        "full_text": transcript.strip(),
        "segments": [{
            "start": 0.0,
            "end": 0.0, # Approximate
            "text": transcript.strip(),
            "speaker": "Speaker 1"
        }]
    }
