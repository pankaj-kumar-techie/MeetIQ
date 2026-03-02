import os, json, asyncio
import google.generativeai as genai

GEMINI_KEY   = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# Configure the SDK once at import time
genai.configure(api_key=GEMINI_KEY)
_model = genai.GenerativeModel(GEMINI_MODEL)

# ── Low-level chat helper ────────────────────────────────────────────────────
async def _chat(system: str, user: str, json_mode: bool = True) -> dict | str:
    prompt = f"{system}\n\n{user}"

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: _model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.15,
                max_output_tokens=2048,
                response_mime_type="application/json" if json_mode else "text/plain",
            ),
        ),
    )

    text = response.text.strip()
    if json_mode:
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    return text


# ── High-level analysis entry point ─────────────────────────────────────────
async def analyze_meeting(
    transcript: str,
    agenda: str = "",
    purpose: str = "",
    meeting_type: str = "discovery",
) -> dict:
    """Run all 4 analyses in parallel. Returns combined dict."""
    context = (
        f"Meeting purpose: {purpose}\n"
        f"Meeting agenda: {agenda}\n"
        f"Meeting type: {meeting_type}\n\n"
        f"Transcript:\n{transcript}"
    )

    results = await asyncio.gather(
        _summarize(context),
        _detect_commitments(transcript),
        _extract_actions(transcript),
        _gen_followup(transcript, purpose),
        return_exceptions=True,
    )

    def safe(r, fallback):
        if isinstance(r, Exception):
            print(f"[Gemini analysis error] {type(r).__name__}: {r}")
            return fallback
        return r

    summary_fallback = {
        "overview": "Analysis unavailable.",
        "key_points": [],
        "decisions": [],
        "open_questions": [],
        "sentiment": "neutral",
        "meeting_type": meeting_type,
    }

    summary = safe(results[0], summary_fallback)
    return {
        "summary":               summary,
        "commitments":           safe(results[1], []),
        "action_items":          safe(results[2], []),
        "follow_up":             safe(results[3], ""),
        "detected_meeting_type": summary.get("meeting_type") if isinstance(summary, dict) else None,
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
