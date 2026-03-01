from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from pgvector.sqlalchemy import Vector
from .database import Base

class Scheme(Base):
    __tablename__ = "schemes"

    # Searchable Metadata
    slug = Column(String, primary_key=True, index=True)
    schemeName = Column(String, nullable=False)
    schemeShortTitle = Column(String)
    level = Column(String)
    nodalMinistryName = Column(String)
    
    # ARRAY types are perfect for lists of strings
    beneficiaryState = Column(ARRAY(String))
    schemeCategory = Column(ARRAY(String))
    tags = Column(ARRAY(String))
    
    briefDescription = Column(String)

    # Vector embeddings for semantic AI search (using AWS Titan's 1536 dimensions)
    embedding = Column(Vector(1536)) 

    # The Deep Details (Stored as a flexible JSONB object)
    deep_details = Column(JSONB)