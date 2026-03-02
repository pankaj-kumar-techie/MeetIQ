from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from core.database import init_db
from routers import recordings, meetings

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Cleanup recordings stuck in "processing" state (orphaned by previous server exit)
    from core.database import AsyncSessionLocal
    from models.recording import Recording
    from sqlalchemy import update
    async with AsyncSessionLocal() as db:
        await db.execute(update(Recording).where(Recording.status == "processing").values(status="error"))
        await db.commit()
        print("[MeetIQ] Startup cleanup: reset 'processing' recordings.")
    yield

app = FastAPI(title="MeetIQ API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(recordings.router, prefix="/api/recordings", tags=["recordings"])
app.include_router(meetings.router,   prefix="/api/meetings",   tags=["meetings"])

@app.get("/health")
async def health(): return {"status": "ok"}
