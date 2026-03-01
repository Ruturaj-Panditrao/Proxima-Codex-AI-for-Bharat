from sqlalchemy import Column, String
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