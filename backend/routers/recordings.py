import os
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from core.database import get_db
from models.recording import Recording, Chunk
from services.transcription import transcribe_chunks
from services.ai_analysis import analyze_meeting
from datetime import datetime

router = APIRouter()

class StartPayload(BaseModel):
    name:         str
    purpose:      str = ""
    agenda:       str = ""
    participants: list[str] = []
    meeting_type: str = "discovery"
    platform:     str = "unknown"

class ChunkPayload(BaseModel):
    chunk: str   # base64 WebM audio

# ── Start a recording session ────────────────────────────────────────────────
@router.post("/start")
async def start_recording(payload: StartPayload, db: AsyncSession = Depends(get_db)):
    rec = Recording(
        name=payload.name,
        purpose=payload.purpose,
        agenda=payload.agenda,
        participants=payload.participants,
        meeting_type=payload.meeting_type,
        platform=payload.platform,
        status="recording",
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return {"recording_id": rec.id, "status": "recording"}

# ── Stream audio chunks (called every ~10s from extension) ───────────────────
@router.post("/{recording_id}/chunk")
async def receive_chunk(recording_id: str, payload: ChunkPayload, db: AsyncSession = Depends(get_db)):
    rec = await db.get(Recording, recording_id)
    if not rec:
        raise HTTPException(404, "Recording not found")
    if rec.status != "recording":
        raise HTTPException(400, f"Recording is {rec.status}, not accepting chunks")

    result = await db.execute(
        select(func.count()).where(Chunk.recording_id == recording_id)
    )
    count = result.scalar() or 0

    chunk = Chunk(recording_id=recording_id, sequence=count, data_b64=payload.chunk)
    db.add(chunk)
    await db.commit()
    print(f"[MeetIQ] Chunk {count} received for {recording_id}")
    return {"ok": True, "chunk_index": count}

# ── Finalize: assemble → transcribe → analyze ────────────────────────────────
@router.post("/{recording_id}/finalize")
async def finalize_recording(
    recording_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    rec = await db.get(Recording, recording_id)
    if not rec:
        raise HTTPException(404, "Recording not found")
    if rec.status == "processing":
        return {"ok": True, "status": "processing"}
    if rec.status == "done":
        return {"ok": True, "status": "done"}
    if rec.status not in ("recording", "error"):
        raise HTTPException(400, f"Cannot finalize recording with status: {rec.status}")

    rec.status   = "processing"
    rec.ended_at = datetime.utcnow()
    await db.commit()

    background_tasks.add_task(_finalize_bg, recording_id)
    return {"ok": True, "status": "processing"}

async def _finalize_bg(recording_id: str):
    from core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            rec = await db.get(Recording, recording_id)
            if not rec:
                print(f"[MeetIQ finalize] Error: Recording {recording_id} not found in DB")
                return

            print(f"[MeetIQ finalize] Starting for {recording_id} ({rec.name})")

            # Fetch all chunks in order
            result = await db.execute(
                select(Chunk)
                .where(Chunk.recording_id == recording_id)
                .order_by(Chunk.sequence)
            )
            chunks = result.scalars().all()
            chunks_b64 = [c.data_b64 for c in chunks]
            
            if not chunks_b64:
                print(f"[MeetIQ finalize] No audio chunks found for {recording_id}. Finishing fast.")
                rec.status = "done"
                rec.ended_at = datetime.utcnow()
                rec.summary = {
                    "overview": "No audio recorded.",
                    "key_points": [],
                    "decisions": [],
                    "open_questions": [],
                    "sentiment": "neutral",
                    "meeting_type": rec.meeting_type
                }
                # Calc duration even for empty
                if rec.started_at:
                    delta = datetime.now(rec.started_at.tzinfo) - rec.started_at
                    rec.duration_ms = int(delta.total_seconds() * 1000)
                await db.commit()
                return

            # 1. Transcribe
            print(f"[MeetIQ finalize] Transcribing {len(chunks_b64)} chunks...")
            tx = await transcribe_chunks(chunks_b64)
            rec.transcript = tx.get("full_text", "")
            rec.segments   = tx.get("segments", [])
            await db.commit()

            # 2. Analyze
            if rec.transcript:
                print(f"[MeetIQ finalize] Analyzing transcript ({len(rec.transcript)} chars)...")
                result_dict = await analyze_meeting(
                    transcript=rec.transcript,
                    agenda=rec.agenda,
                    purpose=rec.purpose,
                    meeting_type=rec.meeting_type,
                )
                rec.summary               = result_dict.get("summary", {})
                rec.commitments           = result_dict.get("commitments", [])
                rec.action_items          = result_dict.get("action_items", [])
                rec.follow_up             = result_dict.get("follow_up", "")
                if result_dict.get("detected_meeting_type"):
                    rec.detected_meeting_type = result_dict["detected_meeting_type"]
            else:
                print(f"[MeetIQ finalize] Transcript is empty, skipping AI analysis")
                rec.summary = {
                    "overview":       "No speech detected in recording.",
                    "key_points":     [],
                    "decisions":      [],
                    "open_questions": [],
                    "sentiment":      "neutral",
                    "meeting_type":   rec.meeting_type,
                }

            rec.status = "done"
            rec.ended_at = datetime.utcnow()
            
            # Use timezone-aware duration if possible
            try:
                if rec.started_at:
                    from datetime import timezone
                    # Safely convert to naive UTC or keep both aware
                    # SQLAlchemy/SQLite often return a naive datetime that represents UTC.
                    # func.now() + timezone column can be tricky.
                    s = rec.started_at.replace(tzinfo=None)
                    e = rec.ended_at.replace(tzinfo=None)
                    delta = e - s
                    rec.duration_ms = int(delta.total_seconds() * 1000)
            except Exception as dt_err:
                print(f"[MeetIQ] Duration calculation warn: {dt_err}")
                rec.duration_ms = 0

            await db.commit()
            print(f"[MeetIQ finalize] Success for {recording_id} (duration: {rec.duration_ms}ms)")

        except Exception as e:
            import traceback
            print(f"[MeetIQ finalize CRITICAL ERROR] {recording_id}: {str(e)}")
            traceback.print_exc()
            async with AsyncSessionLocal() as err_db:
                r = await err_db.get(Recording, recording_id)
                if r:
                    r.status = "error"
                    await err_db.commit()

# ── Debug Log ──────────────────────────────────────────────────────────────
class LogPayload(BaseModel):
    level: str
    tag: str
    message: str

@router.post("/debug/log")
async def receive_debug_log(payload: LogPayload):
    print(f"[EXT-{payload.level.upper()}] {payload.tag}: {payload.message}")
    return {"ok": True}

@router.get("/{recording_id}/status")
async def poll_status(recording_id: str, db: AsyncSession = Depends(get_db)):
    rec = await db.get(Recording, recording_id)
    if not rec:
        raise HTTPException(404, "Not found")

    # Get chunk count for debug
    result = await db.execute(
        select(func.count()).where(Chunk.recording_id == recording_id)
    )
    chunk_count = result.scalar() or 0

    base = {
        "status":                rec.status,
        "has_result":            rec.status == "done",
        "meeting_type":          rec.meeting_type,
        "detected_meeting_type": rec.detected_meeting_type,
        "duration_ms":           rec.duration_ms,
        "chunk_count":           chunk_count,
    }

    if rec.status == "done":
        base.update({
            "summary":      rec.summary,
            "commitments":  rec.commitments,    # ← Promises / Commitments fully returned
            "action_items": rec.action_items,
            "follow_up":    rec.follow_up,
        })

    return base
