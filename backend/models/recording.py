from sqlalchemy import Column, String, Text, DateTime, Integer, JSON
from sqlalchemy.sql import func
from core.database import Base
import uuid

def gen_id(): return str(uuid.uuid4())

class Recording(Base):
    __tablename__ = "recordings"
    id                    = Column(String, primary_key=True, default=gen_id)
    name                  = Column(String, nullable=False)
    purpose               = Column(Text, default="")
    agenda                = Column(Text, default="")
    participants          = Column(JSON, default=list)
    meeting_type          = Column(String, default="discovery")  # user-chosen
    detected_meeting_type = Column(String, nullable=True)         # AI-inferred
    platform              = Column(String, default="unknown")
    started_at            = Column(DateTime(timezone=True), server_default=func.now())
    ended_at              = Column(DateTime(timezone=True), nullable=True)
    status                = Column(String, default="recording")
    transcript            = Column(Text, default="")
    segments              = Column(JSON, default=list)
    summary               = Column(JSON, default=dict)
    commitments           = Column(JSON, default=list)
    action_items          = Column(JSON, default=list)
    follow_up             = Column(Text, default="")
    duration_ms           = Column(Integer, default=0)

class Chunk(Base):
    __tablename__ = "chunks"
    id           = Column(String, primary_key=True, default=gen_id)
    recording_id = Column(String, nullable=False, index=True)
    sequence     = Column(Integer, nullable=False)
    data_b64     = Column(Text, nullable=False)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

# Alias retained for any future imports
Analysis = Recording
