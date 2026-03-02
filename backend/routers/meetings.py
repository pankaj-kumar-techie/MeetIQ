from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from core.database import get_db
from models.recording import Recording

router = APIRouter()

@router.get("/")
async def list_meetings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Recording)
        .where(Recording.status == "done")
        .order_by(desc(Recording.started_at))
        .limit(100)
    )
    return [_summary(r) for r in result.scalars().all()]

@router.get("/{recording_id}")
async def get_meeting(recording_id: str, db: AsyncSession = Depends(get_db)):
    rec = await db.get(Recording, recording_id)
    if not rec:
        raise HTTPException(404, "Meeting not found")
    return {
        **_summary(rec),
        "transcript":  rec.transcript,
        "segments":    rec.segments,
        "summary":     rec.summary,
        "commitments": rec.commitments,
        "action_items":rec.action_items,
        "follow_up":   rec.follow_up,
        "purpose":     rec.purpose,
        "agenda":      rec.agenda,
    }

@router.delete("/{recording_id}")
async def delete_meeting(recording_id: str, db: AsyncSession = Depends(get_db)):
    rec = await db.get(Recording, recording_id)
    if not rec:
        raise HTTPException(404, "Meeting not found")
    await db.delete(rec)
    await db.commit()
    return {"deleted": True}

def _summary(r: Recording):
    return {
        "id":           r.id,
        "name":         r.name,
        "meeting_type": r.meeting_type,
        "participants": r.participants,
        "status":       r.status,
        "platform":     r.platform,
        "duration_ms":  r.duration_ms,
        "started_at":   r.started_at.isoformat() if r.started_at else None,
    }
