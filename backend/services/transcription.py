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
        # 🛡️ Strategy: Join into one file first, then slice with ffmpeg
        # Chrome WebM chunks are designed to be joined byte-by-byte to form one valid file.
        full_webm_raw = b"".join(base64.b64decode(c) for c in chunks_b64)
        
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(full_webm_raw)
            main_path = f.name
            
        all_text = []
        all_segments = []
        
        num_windows = 0
        try:
            # 🚀 Use ffprobe to get exact duration of the merged file
            import subprocess
            probe = subprocess.run([
                "ffprobe", "-v", "error", "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", main_path
            ], capture_output=True, text=True, check=True)
            total_duration = float(probe.stdout.strip())
            num_windows = int((total_duration + 19) // 20)
            print(f"[TIMING] Sarvam FFmpeg: File duration is {total_duration}s. Slicing into {num_windows} windows.")
        except Exception as probe_err:
            print(f"[FFprobe Error] Falling back to chunk count estimation: {probe_err}")
            num_windows = (len(chunks_b64) + 1) // 2

        try:
            for i in range(num_windows):
                start_sec = i * 20
                # Skip if start is past total duration (safety)
                if 'total_duration' in locals() and start_sec >= total_duration:
                    break

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f_wav:
                    window_path = f_wav.name

                try:
                    # 🚀 Use FFmpeg for high-fidelity slicing
                    import subprocess
                    subprocess.run([
                        "ffmpeg", "-y", "-i", main_path, 
                        "-ss", str(start_sec), "-t", "20", 
                        "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                        window_path
                    ], capture_output=True, check=True)

                    # Final safety check: ensure the resulting file has actual data
                    if os.path.getsize(window_path) < 1000: # Barely a header
                        print(f"[TIMING] Skipping empty window {i+1}")
                        continue

                    print(f"[TIMING] Transcribing window {i+1} (starts at {start_sec}s)...")
                    res = await _sarvam_transcribe(window_path)
                    
                    all_text.append(res["full_text"])
                    for seg in res["segments"]:
                        seg["start"] += start_sec
                        seg["end"] += start_sec
                        all_segments.append(seg)
                except Exception as slice_err:
                    print(f"[FFmpeg Slicing Error] window {i+1}: {slice_err}")
                finally:
                    if os.path.exists(window_path): os.unlink(window_path)
        finally:
            if os.path.exists(main_path): os.unlink(main_path)
        
        return {
            "full_text": " ".join(all_text).strip(),
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
        import requests
        if not SARVAM_KEY or len(SARVAM_KEY) < 20:
             raise Exception("Invalid SARVAM_API_KEY. Please update .env")
             
        # Switch to REST API for reliable parameter support (with_timestamps)
        url = "https://api.sarvam.ai/speech-to-text"
        
        # Determine mime type
        mime = "audio/wav" if file_path.endswith(".wav") else "audio/webm"
        
        files = {
            'file': (os.path.basename(file_path), open(file_path, 'rb'), mime)
        }
        data = {
            'model': SARVAM_MODEL,
            'mode': 'transcribe',
            'with_timestamps': 'true' # 🚀 Official docs param
        }
        headers = {
            'api-subscription-key': SARVAM_KEY
        }
        
        try:
            response = requests.post(url, files=files, data=data, headers=headers)
            if response.status_code != 200:
                print(f"[Sarvam STT Error] {response.status_code}: {response.text}")
                response.raise_for_status()
            return response.json()
        except Exception as stt_err:
            print(f"[Sarvam STT EXCEPTION] {stt_err}")
            raise stt_err
        finally:
            files['file'][1].close()

    res = await loop.run_in_executor(None, _do_sarvam_transcribe)

    def _safe_float(v):
        """Handle cases where Sarvam returns timestamps as numbers, strings, or lists."""
        if isinstance(v, list): return float(v[0]) if v else 0.0
        try: return float(v) if v is not None else 0.0
        except: return 0.0

    # 🚀 Extremely Robust Parsing for Saaras v3 / v2.5 results
    full_text = ""
    segments = []
    
    if isinstance(res, dict):
        full_text = res.get("transcript", "")
        ts_data = res.get("timestamps")
        
        # 1. Attempt word-level segmenting (preferred for Chat UI)
        if ts_data and isinstance(ts_data, dict):
            words = ts_data.get("words", [])
            # Group words into logical segments based on sentence endings or fixed blocks
            current_segment = []
            for idx, w in enumerate(words):
                if isinstance(w, dict):
                    txt = w.get("word", "").strip()
                    current_segment.append(w)
                    # Break segment on sentence delimiters or if it gets too long
                    if txt.endswith((".", "?", "!")) or len(current_segment) >= 20:
                        batch_txt = [win.get("word", "") for win in current_segment]
                        start = _safe_float(current_segment[0].get("start_time_seconds"))
                        end = _safe_float(current_segment[-1].get("end_time_seconds"))
                        segments.append({
                            "start": start,
                            "end": end,
                            "text": " ".join(batch_txt),
                            "speaker": "Participant"
                        })
                        current_segment = []
                else:
                    # Strings fallback
                    segments.append({
                        "start": _safe_float(ts_data.get("start_time_seconds")),
                        "end": _safe_float(ts_data.get("end_time_seconds")),
                        "text": str(w),
                        "speaker": "Participant"
                    })

            # Catch remaining words
            if current_segment:
                batch_txt = [win.get("word", "") for win in current_segment]
                start = _safe_float(current_segment[0].get("start_time_seconds"))
                end = _safe_float(current_segment[-1].get("end_time_seconds"))
                segments.append({
                    "start": start,
                    "end": end,
                    "text": " ".join(batch_txt),
                    "speaker": "Participant"
                })
    elif hasattr(res, "transcript"):
        full_text = res.transcript

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
