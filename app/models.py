from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, func, Text
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from .database import Base
from pgvector.sqlalchemy import Vector

class Scheme(Base):
    __tablename__ = "schemes"

    # Searchable Metadata
    slug = Column(String, primary_key=True, index=True)
    schemeName = Column(String, nullable=False)
    schemeShortTitle = Column(String)
    level = Column(String)
    nodalMinistryName = Column(String)
    
    # FIX 3: schemeFor is a String ("Individual"), not an ARRAY
    schemeFor = Column(String) 
    schemeCloseDate = Column(String)
    
    # ARRAY types are perfect for lists of strings
    beneficiaryState = Column(ARRAY(String))
    schemeCategory = Column(ARRAY(String))
    tags = Column(ARRAY(String))
    
    briefDescription = Column(String)
    
    embedding = Column(Vector(1024))

    # The Deep Details (Stored as a flexible JSONB object)
    deep_details = Column(JSONB)


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    session_id = Column(String, primary_key=True, index=True)
    language_code = Column(String, nullable=True)
    slots = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AgentTurn(Base):
    __tablename__ = "agent_turns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("agent_sessions.session_id", ondelete="CASCADE"), index=True, nullable=False)
    role = Column(String, nullable=False)
    message_text = Column(Text, nullable=False)
    meta = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
