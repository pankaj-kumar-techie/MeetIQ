import os, json, asyncio
import google.generativeai as genai
from openai import AsyncOpenAI

# ── Configuration ────────────────────────────────────────────────────────────
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower() # "gemini", "openai", or "openrouter"

# Gemini Config
GEMINI_KEY   = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    _gemini_model = genai.GenerativeModel(GEMINI_MODEL)

# OpenAI / OpenRouter Config
OPENAI_KEY = os.getenv("OPEN_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "bytedance-seed/seed-2.0-mini")

# Initialize client based on provider
if AI_PROVIDER == "openrouter":
    _openai_client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_KEY,
        default_headers={
            "HTTP-Referer": "https://meetiq.ai", # Optional
            "X-OpenRouter-Title": "MeetIQ",
        }
    )
    OPENAI_MODEL = OPENROUTER_MODEL # Override model for openrouter
elif AI_PROVIDER == "openai":
    _openai_client = AsyncOpenAI(api_key=OPENAI_KEY)
else:
    _openai_client = None

# ── Low-level chat helper ────────────────────────────────────────────────────
async def _chat(system: str, user: str, json_mode: bool = True) -> dict | str:
    # Token Optimization: Truncate very long transcripts to save tokens
    # Approx 4 characters per token, 15k chars is ~3.7k tokens
    if len(user) > 15000:
        user = user[:15000] + "... [Transcript truncated to optimize tokens]"

    if (AI_PROVIDER == "openai" or AI_PROVIDER == "openrouter") and _openai_client:
        return await _chat_openai(system, user, json_mode)
    return await _chat_gemini(system, user, json_mode)

async def _chat_gemini(system: str, user: str, json_mode: bool = True) -> dict | str:
    prompt = f"{system}\n\n{user}"
    loop = asyncio.get_event_loop()
    try:
        response = await loop.run_in_executor(
            None,
            lambda: _gemini_model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=1024 if json_mode else 1536,
                    response_mime_type="application/json" if json_mode else "text/plain",
                ),
            ),
        )
        text = response.text.strip()
    except Exception as e:
        print(f"[Gemini Error] {e}")
        raise e

    if json_mode:
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"): text = text[4:]
        return json.loads(text.strip())
    return text

async def _chat_openai(system: str, user: str, json_mode: bool = True) -> dict | str:
    try:
        response = await _openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            response_format={"type": "json_object"} if json_mode else None,
            temperature=0.1,
            max_tokens=1024 if json_mode else 1536,
        )
        text = response.choices[0].message.content.strip()
        return json.loads(text) if json_mode else text
    except Exception as e:
        print(f"[OpenAI Error] {e}")
        raise e


# ── High-level analysis entry point ─────────────────────────────────────────
async def analyze_meeting(
    transcript: str,
    agenda: str = "",
    purpose: str = "",
    meeting_type: str = "discovery",
) -> dict:
    import time
    start_time = time.time()
    """Consolidated single-pass analysis to save ~75% on input tokens."""
    
    # Simple truncation for safety
    if len(transcript) > 15000:
        transcript = transcript[:15000] + "... [truncated]"

    system_prompt = """You are a highly efficient meeting intelligence engine. 
Analyze the transcript and return a single JSON object with these exact keys:
{
  "summary": {
    "overview": "2-sentence summary",
    "key_points": ["4-6 points"],
    "decisions": ["decisions made"],
    "open_questions": ["unresolved items"],
    "sentiment": "positive|neutral|concerned|negative",
    "meeting_type": "sales|discovery|internal|etc"
  },
  "commitments": [
    {"text": "sentence", "speaker": "who", "type": "promise", "risk_level": "low|med|high"}
  ],
  "action_items": [
    {"task": "description", "owner": "name", "deadline": "date", "priority": "high|low"}
  ],
  "follow_up_email": "A professional plain-text email ready to send."
}"""

    user_context = (
        f"Context:\nPurpose: {purpose}\nAgenda: {agenda}\nType: {meeting_type}\n\n"
        f"Transcript:\n{transcript}"
    )

    try:
        # One call instead of four!
        print(f"[TIMING] Starting AI Analysis via {AI_PROVIDER}...")
        result = await _chat(system_prompt, user_context, json_mode=True)
        
        print(f"[TIMING] AI Analysis complete. Took {time.time() - start_time:.2f}s")
        return {
            "summary": result.get("summary", {}),
            "commitments": result.get("commitments", []),
            "action_items": result.get("action_items", []),
            "follow_up": result.get("follow_up_email", ""),
            "detected_meeting_type": result.get("summary", {}).get("meeting_type"),
        }
    except Exception as e:
        print(f"[MeetIQ Analysis Error] {e}")
        return {
            "summary": {"overview": "Analysis failed.", "key_points": []},
            "commitments": [],
            "action_items": [],
            "follow_up": "",
            "detected_meeting_type": None
        }


# ── Individual analysis passes ───────────────────────────────────────────────
async def _summarize(context: str) -> dict:
    return await _chat(
        """You are a professional meeting analyst. Analyze the transcript and return ONLY valid JSON:
{
  "overview": "2-sentence summary of what the meeting covered and its outcome",
  "key_points": ["4-6 most important discussion points"],
  "decisions": ["concrete decisions made"],
  "open_questions": ["unresolved questions or unclear items"],
  "sentiment": "positive|neutral|concerned|negative",
  "meeting_type": "sales_call|interview|discovery|internal|support|kickoff|status_update|technical_review"
}""",
        context,
    )


async def _detect_commitments(transcript: str) -> list:
    result = await _chat(
        """You are a commitment detection engine. Find EVERY sentence where anyone makes a promise,
deadline commitment, cost estimate, feature agreement, or statement of intent.

Return ONLY valid JSON:
{
  "commitments": [
    {
      "text": "exact commitment sentence",
      "speaker": "client|team|unknown",
      "type": "delivery_promise|budget_mention|timeline_statement|feature_agreement|follow_up_promise",
      "risk_level": "low|medium|high"
    }
  ]
}

Risk level guide:
- high: specific deadline or cost with no buffer ("we ship Friday", "$5k fixed")
- medium: vague commitment with implied deadline
- low: general intent without specifics

Look for: "we will", "I will", "by [date]", "that will cost", "I can deliver",
"definitely", "guaranteed", "I promise", "we'll send", "I'll follow up" """,
        f"Transcript:\n{transcript}",
    )
    return result.get("commitments", [])


async def _extract_actions(transcript: str) -> list:
    result = await _chat(
        """Extract all action items — specific tasks to complete after this meeting.

Return ONLY valid JSON:
{
  "action_items": [
    {
      "task": "clear actionable task description",
      "owner": "client|team|[name if mentioned]",
      "deadline": "specific date or 'Not specified'",
      "priority": "high|medium|low",
      "source_quote": "short phrase from transcript (max 60 chars)"
    }
  ]
}

Priority guide:
- high: mentioned urgently or has a specific deadline
- medium: clearly needed but no urgency
- low: nice-to-have or follow-up""",
        f"Transcript:\n{transcript}",
    )
    return result.get("action_items", [])


async def _gen_followup(transcript: str, purpose: str) -> str:
    return await _chat(
        f"""Write a professional follow-up email based on this meeting.
Meeting purpose: {purpose}

Rules:
- Warm, brief thank-you opener (1 sentence)
- Requirements summary in 3-5 bullet points
- Clear next steps section
- Timeline if discussed
- Professional closing with call to action
- 180-250 words total
- Write it ready to send — no [placeholders]
- Plain text only, no JSON, no markdown headers""",
        f"Transcript:\n{transcript}",
        json_mode=False,
    )
